"""Ciclo de vida de un ticket. Toda transición de estado pasa por aquí (nunca `ticket.estado = …` en una vista).

pendiente ──▶ procesando ──▶ procesado
    ▲             │   └────▶ revisar ──(confirmar)──▶ procesado
    │             └────────▶ error
    └──────── (reprocesar) ── revisar / error
"""

from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.forms.models import model_to_dict
from django.utils import timezone

from core.auditoria import registrar
from core.models import RegistroAuditoria
from finanzas.models import Movimiento
from finanzas.servicios_comercios import reconocer_o_crear_comercio, sugerir_categoria

from . import ocr
from .exceptions import EstadoNoPermitido
from .ia import ClienteIA, breaker_ia
from .models import LineaTicket, Ticket
from .signals import ticket_terminado

E = Ticket.Estado
TOLERANCIA_SUMA = Decimal("0.05")


def _encolar(ticket_id: int) -> None:
    from .tasks import procesar_ticket  # evita la importación circular tasks ↔ services

    # on_commit: si la transacción se deshace, no se encola nada; y el worker nunca lee un ticket aún sin guardar
    transaction.on_commit(lambda: procesar_ticket.delay(ticket_id))


def _terminado(ticket: Ticket) -> None:
    transaction.on_commit(lambda: ticket_terminado.send(sender=Ticket, ticket=ticket))


# ── 1. Subida ──
def subir(*, hogar, cuenta, archivo, tipo: str, huella_archivo: str, usuario) -> Ticket:
    ticket = Ticket.objects.create(
        hogar=hogar,
        cuenta=cuenta,
        subido_por=usuario,
        archivo=archivo,
        nombre_original=archivo.name[:200],
        tipo=tipo,
        huella_archivo=huella_archivo,
    )
    _encolar(ticket.pk)
    return ticket


# ── 2. Procesado (lo llama la tarea de Celery) ──
def empezar(ticket_id: int) -> Ticket | None:
    """Reclama el ticket con un UPDATE condicional (atómico). None si ya no hay nada que hacer.

    Se admite `procesando` para que los reintentos de la tarea puedan continuar.
    """
    reclamado = Ticket.objects.filter(pk=ticket_id, estado__in=[E.PENDIENTE, E.PROCESANDO]).update(
        estado=E.PROCESANDO, intentos=F("intentos") + 1, error=""
    )
    return Ticket.objects.select_related("hogar").get(pk=ticket_id) if reclamado else None


def leer(ticket: Ticket) -> tuple[str, bytes | None]:
    """Texto del ticket (reutiliza el de un intento anterior) y la imagen si el OCR no ha servido."""
    if len(ticket.texto_ocr.strip()) >= ocr.MIN_CARACTERES:
        return ticket.texto_ocr, None
    with ticket.archivo.open("rb") as f:
        lectura = ocr.leer(f.read(), ticket.tipo)
    Ticket.objects.filter(pk=ticket.pk).update(texto_ocr=lectura.texto)
    ticket.texto_ocr = lectura.texto
    return lectura.texto, None if lectura.es_util else lectura.imagen_png


def procesar(ticket: Ticket) -> Ticket:
    texto, imagen = leer(ticket)
    categorias = list(ticket.hogar.categorias.values_list("nombre", flat=True))
    with ClienteIA.desde_settings() as cliente:
        datos = breaker_ia.llamar(cliente.extraer_ticket, texto, categorias, imagen)
    return aplicar(ticket.pk, datos)


def motivos_de_revision(datos: dict) -> list[str]:
    motivos = []
    hoy = timezone.localdate()
    if datos["confianza"] < settings.TICKETS_UMBRAL_CONFIANZA:
        motivos.append(f"La IA no está segura ({datos['confianza']:.2f}).")
    if datos["total"] is None:
        motivos.append("No se ha encontrado el total.")
    if datos["fecha"] is None:
        motivos.append("No se ha encontrado la fecha.")
    elif not hoy - timedelta(days=365) <= datos["fecha"] <= hoy:
        motivos.append("La fecha no es plausible.")
    if not datos["comercio"]:
        motivos.append("No se ha encontrado el comercio.")
    if datos["lineas"] and datos["total"] is not None:
        suma = sum(linea["cantidad"] * linea["precio_unitario"] for linea in datos["lineas"])
        if abs(suma - datos["total"]) > TOLERANCIA_SUMA:
            motivos.append(f"Las líneas suman {suma:.2f} y el total es {datos['total']}.")
    return motivos


@transaction.atomic
def aplicar(ticket_id: int, datos: dict) -> Ticket:
    """Guarda lo extraído y crea el gasto. El bloqueo hace que una entrega duplicada de la tarea no cree otro."""
    ticket = Ticket.objects.select_for_update().select_related("hogar", "cuenta").get(pk=ticket_id)
    if ticket.estado != E.PROCESANDO:
        return ticket  # otro worker ya lo terminó

    ticket.lineas.all().delete()
    LineaTicket.objects.bulk_create(
        LineaTicket(
            ticket=ticket,
            orden=i,
            descripcion=linea["descripcion"],
            cantidad=linea["cantidad"],
            precio_unitario=linea["precio_unitario"],
        )
        for i, linea in enumerate(datos["lineas"], start=1)
    )
    comercio = reconocer_o_crear_comercio(datos["comercio"], datos.get("nif", ""))
    motivos = motivos_de_revision(datos)

    if datos["total"] is not None:  # sin total no se puede crear el gasto: el usuario lo completará
        ticket.movimiento = Movimiento.objects.create(
            hogar=ticket.hogar,
            cuenta=ticket.cuenta,
            fecha=datos["fecha"] or timezone.localdate(),
            importe=-datos["total"],
            concepto=(comercio.nombre if comercio else datos["comercio"]) or "Ticket",
            comercio=comercio,
            categoria=sugerir_categoria(ticket.hogar, comercio, datos["categoria"]),
            origen=Movimiento.Origen.TICKET,
            revisado=not motivos,
            creado_por=ticket.subido_por,
        )

    ticket.datos_ia = datos
    ticket.confianza = Decimal(str(round(datos["confianza"], 2)))
    ticket.estado = E.REVISAR if motivos else E.PROCESADO
    ticket.error = "\n".join(motivos)
    ticket.procesado_en = timezone.now()
    ticket.save()
    _terminado(ticket)
    return ticket


def marcar_error(ticket_id: int, mensaje: str, estado: str = E.ERROR) -> None:
    """Termina sin gasto: `error` (se puede reprocesar) o `revisar` (el usuario introduce los datos a mano)."""
    with transaction.atomic():
        actualizados = Ticket.objects.filter(pk=ticket_id, estado__in=[E.PENDIENTE, E.PROCESANDO]).update(
            estado=estado, error=mensaje[:1000], procesado_en=timezone.now()
        )
        if actualizados:
            _terminado(Ticket.objects.get(pk=ticket_id))


# ── 3. Acciones del usuario ──
@transaction.atomic
def confirmar(ticket: Ticket, *, datos: dict, usuario) -> Ticket:
    """El usuario revisa (y corrige) lo que propuso la IA. Crea o actualiza el gasto y lo marca como revisado."""
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    if ticket.estado != E.REVISAR:
        raise EstadoNoPermitido()
    campos = {
        "fecha": datos["fecha"],
        "importe": -datos["total"],
        "concepto": datos["concepto"],
        "categoria": datos.get("categoria"),
        "revisado": True,
    }
    if (mov := ticket.movimiento) is not None:
        antes = model_to_dict(mov)
        for campo, valor in campos.items():
            setattr(mov, campo, valor)
        mov.save()
        registrar(mov, RegistroAuditoria.Accion.MODIFICAR, usuario, antes=antes)
    else:
        mov = Movimiento.objects.create(
            hogar_id=ticket.hogar_id,
            cuenta_id=ticket.cuenta_id,
            origen=Movimiento.Origen.TICKET,
            creado_por=usuario,
            comercio=reconocer_o_crear_comercio(datos["concepto"]),
            **campos,
        )
        registrar(mov, RegistroAuditoria.Accion.CREAR, usuario)
    ticket.movimiento = mov
    ticket.estado = E.PROCESADO
    ticket.save(update_fields=["movimiento", "estado", "actualizado"])
    return ticket


@transaction.atomic
def reprocesar(ticket: Ticket, *, repetir_ocr: bool = False) -> Ticket:
    ticket = Ticket.objects.select_for_update().get(pk=ticket.pk)
    if ticket.estado not in (E.REVISAR, E.ERROR):
        raise EstadoNoPermitido()
    if ticket.movimiento is not None and not ticket.movimiento.revisado:
        ticket.movimiento.delete()  # el gasto propuesto se descarta; uno ya revisado no se toca
    ticket.movimiento = None
    ticket.lineas.all().delete()
    ticket.estado, ticket.intentos, ticket.error = E.PENDIENTE, 0, ""
    ticket.datos_ia, ticket.confianza, ticket.procesado_en = {}, None, None
    if repetir_ocr:
        ticket.texto_ocr = ""
    ticket.save()
    _encolar(ticket.pk)
    return ticket


def borrar(ticket: Ticket) -> None:
    """Borra el ticket y, cuando la transacción se confirma, su archivo (el gasto, si existe, se queda)."""
    nombre, storage = ticket.archivo.name, ticket.archivo.storage
    ticket.delete()
    transaction.on_commit(lambda: storage.delete(nombre))
