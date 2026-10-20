from datetime import date
from decimal import Decimal

from django.conf import settings
from django.core import signing
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import Coalesce
from django.template.loader import render_to_string
from django.utils import formats, timezone, translation
from weasyprint import HTML

from finanzas import dashboard
from finanzas.models import Movimiento
from hogares.models import Hogar

from .models import InformeMensual
from .signals import informe_generado

T = InformeMensual.Tipo
CERO = Decimal("0")


# ── Gráfico SVG (ejercicio 2): la plantilla solo dibuja; las cuentas se hacen aquí ──
def grafico_evolucion(evolucion: list[dict], ancho: int = 500, alto: int = 110) -> dict:
    maximo = max([max(m["gastos"], m["ingresos"]) for m in evolucion] + [Decimal("1")])
    paso = ancho / len(evolucion)
    barra = paso * 0.36

    def altura(valor):
        return round(float(valor / maximo) * alto, 1)

    barras = []
    for i, m in enumerate(evolucion):
        x = round(i * paso + paso * 0.12, 1)
        g, ing = altura(m["gastos"]), altura(m["ingresos"])
        barras.append(
            {
                "x_gasto": x,
                "x_ingreso": round(x + barra, 1),
                "ancho": round(barra, 1),
                "y_gasto": round(alto - g, 1),
                "alto_gasto": g,
                "y_ingreso": round(alto - ing, 1),
                "alto_ingreso": ing,
                "x_texto": round(x + barra, 1),
                "etiqueta": f"{m['mes']:%m/%y}",
            }
        )
    return {"ancho": ancho, "alto": alto, "alto_total": alto + 14, "barras": barras}


def contexto(hogar: Hogar, mes: date) -> dict:
    resumen = dashboard.calcular(hogar, mes)  # los mismos números que el dashboard (módulo 77)
    return {
        "hogar": hogar,
        "resumen": resumen,
        "grafico": grafico_evolucion(resumen["evolucion"]),
        "movimientos": (
            Movimiento.objects.del_hogar(hogar)
            .del_mes(mes)
            .con_detalle()
            # {% regroup %} agrupa elementos CONSECUTIVOS: la lista debe venir ordenada por el grupo
            .order_by("categoria__nombre", "categoria_id", "fecha", "id")
        ),
        "generado": timezone.localtime(),
    }


def contexto_anual(hogar: Hogar, anio: int) -> dict:
    """Ejercicio 4: el año entero con las mismas piezas del dashboard, sobre un rango de 12 meses."""
    del_anio = Movimiento.objects.del_hogar(hogar).filter(fecha__gte=date(anio, 1, 1), fecha__lt=date(anio + 1, 1, 1))
    t = del_anio.aggregate(
        gastos=Coalesce(Sum("importe", filter=Q(importe__lt=0)), CERO),
        ingresos=Coalesce(Sum("importe", filter=Q(importe__gt=0)), CERO),
        num=Count("id"),
    )
    evolucion = [m | {"balance": m["ingresos"] - m["gastos"]} for m in dashboard.evolucion(hogar, date(anio, 12, 1))]
    return {
        "hogar": hogar,
        "anio": anio,
        "resumen": {
            "gastos": -t["gastos"],
            "ingresos": t["ingresos"],
            "balance": t["ingresos"] + t["gastos"],
            "num_movimientos": t["num"],
            "por_categoria": dashboard.por_categoria(del_anio),
            "evolucion": evolucion,
            "top_comercios": list(
                del_anio.gastos()
                .filter(comercio__isnull=False)
                .values("comercio", nombre=F("comercio__nombre"))
                .annotate(total=-Sum("importe"), veces=Count("id"))
                .order_by("-total")[:10]
            ),
        },
        "grafico": grafico_evolucion(evolucion),
        "generado": timezone.localtime(),
    }


def pdf(hogar: Hogar, mes: date, idioma: str | None = None, tipo: str = T.MENSUAL) -> bytes:
    with translation.override(idioma or settings.LANGUAGE_CODE):
        if tipo == T.ANUAL:
            html = render_to_string("informes/anual.html", contexto_anual(hogar, mes.year))
        else:
            html = render_to_string("informes/mensual.html", contexto(hogar, mes))
    return HTML(string=html).write_pdf()


def generar(hogar_id: int, mes: date, *, tipo: str = T.MENSUAL, usuario=None, enviar: bool = True) -> InformeMensual:
    """Genera (o regenera) el PDF. Idempotente: un informe por hogar, tipo y periodo (restricción única)."""
    hogar = Hogar.objects.get(pk=hogar_id)
    if tipo == T.ANUAL:
        mes = mes.replace(month=1, day=1)
    contenido = pdf(hogar, mes, tipo=tipo)  # fuera de la transacción: puede tardar segundos
    with transaction.atomic():
        informe = InformeMensual.objects.select_for_update().filter(hogar=hogar, tipo=tipo, mes=mes).first()
        anterior = informe.archivo.name if informe else None
        if informe is None:
            informe = InformeMensual(hogar=hogar, tipo=tipo, mes=mes)
        informe.generado_por = usuario
        informe.tamano = len(contenido)
        informe.archivo.save("informe.pdf", ContentFile(contenido), save=False)
        informe.save()
        if anterior:
            storage = informe.archivo.storage
            transaction.on_commit(lambda: storage.delete(anterior))
        transaction.on_commit(lambda: informe_generado.send(sender=InformeMensual, informe=informe, enviar=enviar))
        if enviar:
            transaction.on_commit(lambda: enviar_a_miembros(informe))
    return informe


def enviar_a_miembros(informe: InformeMensual) -> None:
    from .tasks import enviar_informe

    destinatarios = informe.hogar.membresias.filter(
        usuario__is_active=True,
        usuario__recibir_informes=True,  # ejercicio 3: quien se dio de baja, no
    ).values_list("usuario_id", flat=True)
    for usuario_id in destinatarios:
        enviar_informe.enqueue(informe.pk, usuario_id)


def nombre_periodo(informe: InformeMensual) -> str:
    """ "octubre de 2026" / "2026", en el idioma activo."""
    return f"{informe.mes:%Y}" if informe.es_anual else formats.date_format(informe.mes, "F Y")


# ── Baja de los emails de informes (ejercicio 3) ──
SAL_BAJA = "informes.baja"


def token_baja(usuario) -> str:
    # Firmado con SECRET_KEY (y aceptado con SECRET_KEY_FALLBACKS al rotar). Sin caducidad a propósito:
    # un enlace de baja de un email de hace un año tiene que seguir funcionando.
    return signing.dumps(usuario.pk, salt=SAL_BAJA)


def usuario_de_token(token: str):
    from django.contrib.auth import get_user_model

    try:
        return get_user_model().objects.filter(pk=signing.loads(token, salt=SAL_BAJA)).first()
    except signing.BadSignature:
        return None


def dar_de_baja(token: str) -> bool:
    usuario = usuario_de_token(token)
    if usuario is None:
        return False
    if usuario.recibir_informes:
        usuario.recibir_informes = False
        usuario.save(update_fields=["recibir_informes"])
    return True
