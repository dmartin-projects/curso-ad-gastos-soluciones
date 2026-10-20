"""Importación de extractos en dos fases: análisis con vista previa y, tras confirmar, importación por lotes.

pendiente ─▶ analizando ─▶ vista_previa ─(confirmar)─▶ importando ─▶ completada ─(deshacer)─▶ deshecha
                 └────────────────────────────────────────┴─▶ error
"""

from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from finanzas.models import Movimiento
from finanzas.normalizacion import normalizar
from finanzas.servicios_comercios import reconocer_comercio, sugerir_categoria
from finanzas.signals import movimientos_cambiados

from . import lectores
from .deduplicacion import huellas
from .exceptions import EstadoNoPermitido
from .models import FilaImportacion, Importacion
from .signals import importacion_analizada, importacion_progreso, importacion_terminada

E = Importacion.Estado
A = FilaImportacion.Accion


def _avisar(senal, importacion_id: int) -> None:
    transaction.on_commit(
        lambda: senal.send(sender=Importacion, importacion=Importacion.objects.get(pk=importacion_id))
    )


# ── 1. Subida ──
def subir(*, hogar, cuenta, archivo, formato: str, huella_archivo: str, usuario, perfil=None) -> Importacion:
    from .tasks import analizar_importacion

    importacion = Importacion.objects.create(
        hogar=hogar,
        cuenta=cuenta,
        subido_por=usuario,
        archivo=archivo,
        nombre_original=archivo.name[:200],
        formato=formato,
        huella_archivo=huella_archivo,
        perfil=perfil,
    )
    transaction.on_commit(lambda: analizar_importacion.delay(importacion.pk))
    return importacion


# ── 2. Análisis: leer, normalizar y clasificar cada fila (sin crear ningún movimiento) ──
def analizar(importacion_id: int) -> Importacion | None:
    if not Importacion.objects.filter(pk=importacion_id, estado=E.PENDIENTE).update(estado=E.ANALIZANDO):
        return None  # entrega duplicada: otro worker ya lo está analizando
    imp = Importacion.objects.select_related("perfil").get(pk=importacion_id)
    try:
        with imp.archivo.open("rb") as f:
            lectura = lectores.leer(f.read(), imp.formato, imp.perfil.como_lector() if imp.perfil else None)
    except lectores.ExtractoNoValido as e:
        fallar(importacion_id, str(e))
        return None
    if not lectura.filas:
        fallar(importacion_id, "No se ha encontrado ningún movimiento en el archivo.")
        return None

    filas = clasificar(imp, lectura.filas)
    duplicadas = sum(f.accion == A.DUPLICADA for f in filas)
    with transaction.atomic():
        FilaImportacion.objects.bulk_create(filas, batch_size=1000)
        imp.total_filas = len(filas)
        imp.duplicados = duplicadas
        imp.avisos = lectura.avisos
        imp.resumen = {
            "desde": min(f.fecha for f in filas).isoformat(),
            "hasta": max(f.fecha for f in filas).isoformat(),
            "gastos": str(sum(f.importe for f in filas if f.importe < 0)),
            "ingresos": str(sum(f.importe for f in filas if f.importe > 0)),
            "duplicadas": duplicadas,
            "conciliar": sum(f.accion == A.CONCILIAR for f in filas),
            "a_importar": len(filas) - duplicadas,
        }
        imp.estado = E.VISTA_PREVIA
        imp.save()
        _avisar(importacion_analizada, imp.pk)
    return imp


def clasificar(imp: Importacion, leidas: list[lectores.FilaLeida]) -> list[FilaImportacion]:
    """Cada fila: DUPLICADA (ya importada), CONCILIAR (coincide con un gasto manual o de ticket) o CREAR."""
    hs = huellas(imp.cuenta_id, leidas)
    existentes = set(Movimiento.objects.filter(cuenta_id=imp.cuenta_id, huella__in=hs).values_list("huella", flat=True))
    margen = timedelta(days=settings.IMPORTACION_DIAS_CONCILIACION)
    fechas = [f.fecha for f in leidas]
    candidatos = defaultdict(list)  # importe → movimientos de la cuenta sin huella (manuales o de tickets)
    for mov in Movimiento.objects.filter(
        cuenta_id=imp.cuenta_id, huella="", fecha__range=(min(fechas) - margen, max(fechas) + margen)
    ).only("id", "fecha", "importe"):
        candidatos[mov.importe].append(mov)

    filas = []
    for leida, huella in zip(leidas, hs, strict=True):
        fila = FilaImportacion(
            importacion=imp,
            numero=leida.numero,
            fecha=leida.fecha,
            concepto=leida.concepto,
            importe=leida.importe,
            huella=huella,
            accion=A.CREAR,
        )
        if huella in existentes:
            fila.accion = A.DUPLICADA
        elif mov := _emparejar(candidatos[leida.importe], leida.fecha, margen):
            fila.accion, fila.coincide_con = A.CONCILIAR, mov
        filas.append(fila)
    return filas


def _emparejar(movimientos: list[Movimiento], fecha, margen) -> Movimiento | None:
    """El de fecha más cercana dentro del margen; se retira para no emparejarlo con dos filas."""
    cercanos = [m for m in movimientos if abs(m.fecha - fecha) <= margen]
    if not cercanos:
        return None
    mejor = min(cercanos, key=lambda m: abs(m.fecha - fecha))
    movimientos.remove(mejor)
    return mejor


# ── 3. Confirmación e importación por lotes ──
@transaction.atomic
def confirmar(imp: Importacion, *, separar: list[int] = ()) -> Importacion:
    """`separar`: filas marcadas para conciliar que el usuario quiere importar como movimientos nuevos."""
    imp = Importacion.objects.select_for_update().get(pk=imp.pk)
    if imp.estado != E.VISTA_PREVIA:
        raise EstadoNoPermitido()
    if separar:
        imp.filas.filter(pk__in=separar, accion=A.CONCILIAR).update(accion=A.CREAR, coincide_con=None)
    ids = list(imp.filas.exclude(accion=A.DUPLICADA).values_list("pk", flat=True))
    imp.estado, imp.procesadas = E.IMPORTANDO, 0
    imp.save(update_fields=["estado", "procesadas", "actualizado"])

    from .tasks import lanzar_importacion

    transaction.on_commit(lambda: lanzar_importacion(imp.pk, ids))
    return imp


@transaction.atomic
def importar_lote(importacion_id: int, ids: list[int]) -> dict:
    imp = Importacion.objects.select_related("hogar").get(pk=importacion_id)
    if imp.estado != E.IMPORTANDO:
        return {"omitido": True}
    # FOR UPDATE: una entrega duplicada del mismo lote espera aquí y después ya no encuentra filas pendientes
    filas = list(
        FilaImportacion.objects.select_for_update(of=("self",))
        .select_related("coincide_con", "categoria")
        .filter(importacion_id=importacion_id, pk__in=ids, movimiento__isnull=True)
        .exclude(accion=A.DUPLICADA)
    )
    # otra importación (un extracto solapado) puede haber creado alguna desde el análisis
    ya = set(
        Movimiento.objects.filter(cuenta_id=imp.cuenta_id, huella__in=[f.huella for f in filas]).values_list(
            "huella", flat=True
        )
    )
    nuevas, conciliadas, duplicadas = [], [], 0
    for fila in filas:
        if fila.huella in ya:
            fila.accion = A.DUPLICADA
            duplicadas += 1
        elif fila.accion == A.CONCILIAR and fila.coincide_con and not fila.coincide_con.huella:
            fila.coincide_con.huella = fila.huella  # el gasto manual "absorbe" la fila del banco
            fila.movimiento = fila.coincide_con
            conciliadas.append(fila)
        else:
            fila.accion = A.CREAR
            nuevas.append(fila)

    clasificados: dict[str, tuple] = {}  # caché por concepto: el mismo comercio se repite mucho en un extracto

    def comercio_y_categoria(concepto):
        clave = normalizar(concepto)
        if clave not in clasificados:
            comercio = reconocer_comercio(concepto)
            clasificados[clave] = (comercio, sugerir_categoria(imp.hogar, comercio))
        return clasificados[clave]

    movimientos = Movimiento.objects.bulk_create(  # en PostgreSQL devuelve los objetos con su pk
        Movimiento(
            hogar=imp.hogar,
            cuenta_id=imp.cuenta_id,
            fecha=fila.fecha,
            importe=fila.importe,
            concepto=fila.concepto,
            comercio=(cc := comercio_y_categoria(fila.concepto))[0],
            categoria=fila.categoria or cc[1],  # lo que eligió el usuario en la vista previa manda
            origen=Movimiento.Origen.EXTRACTO,
            huella=fila.huella,
            creado_por=imp.subido_por,
        )
        for fila in nuevas
    )
    for fila, mov in zip(nuevas, movimientos, strict=True):
        fila.movimiento = mov
    Movimiento.objects.bulk_update([f.coincide_con for f in conciliadas], ["huella"])
    FilaImportacion.objects.bulk_update(filas, ["accion", "movimiento"])
    Importacion.objects.filter(pk=importacion_id).update(
        procesadas=F("procesadas") + len(ids),
        creados=F("creados") + len(nuevas),
        conciliados=F("conciliados") + len(conciliadas),
        duplicados=F("duplicados") + duplicadas,
    )
    _avisar(importacion_progreso, importacion_id)
    return {"creados": len(nuevas), "conciliados": len(conciliadas), "duplicados": duplicadas}


def _meses(filas) -> set:
    return set(filas.dates("fecha", "month"))


@transaction.atomic
def finalizar(importacion_id: int) -> Importacion:
    imp = Importacion.objects.select_for_update().get(pk=importacion_id)
    if imp.estado != E.IMPORTANDO:
        return imp
    imp.estado, imp.terminado_en = E.COMPLETADA, timezone.now()
    imp.save(update_fields=["estado", "terminado_en", "actualizado"])
    # bulk_create no emite post_save: se avisa explícitamente a quien cachea o vigila presupuestos
    meses = _meses(imp.filas.exclude(movimiento=None))
    transaction.on_commit(lambda: movimientos_cambiados.send(sender=Movimiento, hogar_id=imp.hogar_id, meses=meses))
    _avisar(importacion_terminada, imp.pk)
    return imp


def fallar(importacion_id: int, mensaje: str) -> None:
    with transaction.atomic():
        actualizadas = Importacion.objects.filter(
            pk=importacion_id, estado__in=[E.PENDIENTE, E.ANALIZANDO, E.IMPORTANDO]
        ).update(estado=E.ERROR, error=mensaje[:1000], terminado_en=timezone.now())
        if actualizadas:
            _avisar(importacion_terminada, importacion_id)


# ── 4. Deshacer ──
@transaction.atomic
def deshacer(imp: Importacion) -> Importacion:
    """Borra lo creado por esta importación y devuelve los gastos conciliados a su estado anterior.

    También vale para una importación con error a medias (algunos lotes terminaron y otros no).
    """
    imp = Importacion.objects.select_for_update().get(pk=imp.pk)
    if imp.estado not in (E.COMPLETADA, E.ERROR):
        raise EstadoNoPermitido()
    creadas = imp.filas.filter(accion=A.CREAR, movimiento__isnull=False)
    meses = _meses(creadas)
    Movimiento.objects.filter(pk__in=creadas.values("movimiento")).delete()
    Movimiento.objects.filter(pk__in=imp.filas.filter(accion=A.CONCILIAR).values("movimiento")).update(huella="")
    imp.estado = E.DESHECHA
    imp.save(update_fields=["estado", "actualizado"])
    transaction.on_commit(lambda: movimientos_cambiados.send(sender=Movimiento, hogar_id=imp.hogar_id, meses=meses))
    return imp


# ── 5. Edición de la vista previa ──
@transaction.atomic
def cambiar_categoria(fila: FilaImportacion, categoria) -> FilaImportacion:
    imp = Importacion.objects.select_for_update().get(pk=fila.importacion_id)  # serializa con confirmar()
    if imp.estado != E.VISTA_PREVIA:
        raise EstadoNoPermitido()  # ya se está importando: cambiarla ahora no tendría efecto
    fila.categoria = categoria
    fila.save(update_fields=["categoria"])
    return fila


# ── 6. Caducidad ──
def caducar(dias: int = 7) -> int:
    """Borra las vistas previas abandonadas (con sus filas y su archivo). La lanza Celery Beat cada noche."""
    limite = timezone.now() - timedelta(days=dias)
    with transaction.atomic():
        # FOR UPDATE SKIP LOCKED: si alguien está confirmando una justo ahora, se deja para mañana
        viejas = list(
            Importacion.objects.select_for_update(skip_locked=True)
            .filter(estado=E.VISTA_PREVIA, actualizado__lt=limite)
            .only("id", "archivo")
        )
        archivos = [(i.archivo.storage, i.archivo.name) for i in viejas]
        Importacion.objects.filter(pk__in=[i.pk for i in viejas]).delete()  # CASCADE: también sus filas
        # el archivo, solo si el borrado se confirma (si no, quedaría una importación sin archivo)
        transaction.on_commit(lambda: [storage.delete(nombre) for storage, nombre in archivos])
    return len(viejas)
