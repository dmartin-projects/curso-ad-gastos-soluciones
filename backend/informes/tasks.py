import logging
from datetime import date
from email.headerregistry import Address
from zoneinfo import ZoneInfo

from celery import shared_task
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import EmailMultiAlternatives
from django.tasks import task
from django.template.loader import render_to_string
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from finanzas import dashboard
from finanzas.models import Movimiento
from hogares.models import Hogar

from . import services
from .models import InformeMensual

logger = logging.getLogger(__name__)


HORA_INFORMES = 7


def mes_a_informar(ahora_local) -> date | None:
    """El mes cuyo informe toca en esa zona: el anterior, si allí es día 1 y ya son las 7:00. Si no, None."""
    if ahora_local.day != 1 or ahora_local.hour < HORA_INFORMES:
        return None
    return dashboard.mes_anterior(ahora_local.date())


@shared_task(ignore_result=True)
def generar_informes_mensuales() -> int:
    """Coordinadora, CADA HORA (ejercicio 1): en cada zona horaria donde ya son las 7:00 del día 1, encola UNA
    tarea por hogar que aún no tenga su informe (módulo 26). Durante el resto del día 1 recoge los que una
    hora caída se dejara; el `exclude` hace que relanzarla no duplique nada."""
    ahora, total = timezone.now(), 0
    for zona in Hogar.objects.order_by().values_list("zona_horaria", flat=True).distinct():
        if (mes := mes_a_informar(ahora.astimezone(ZoneInfo(zona)))) is None:
            continue
        con_movimientos = Movimiento.objects.del_mes(mes).values("hogar_id").distinct()
        ya_hechos = InformeMensual.objects.filter(tipo=InformeMensual.Tipo.MENSUAL, mes=mes).values("hogar_id")
        pendientes = (
            Hogar.objects.filter(zona_horaria=zona, pk__in=con_movimientos)
            .exclude(pk__in=ya_hechos)
            .values_list("pk", flat=True)
        )
        for hogar_id in pendientes:
            generar_informe.delay(hogar_id, mes.isoformat())
        logger.info("Informes de %s encolados en %s: %s", f"{mes:%Y-%m}", zona, len(pendientes))
        total += len(pendientes)
    return total


@shared_task(ignore_result=True)
def generar_informes_anuales() -> int:
    """El 2 de enero (ejercicio 4): el informe del año anterior para cada hogar con movimientos en él."""
    anio = timezone.localdate().year - 1
    enero = date(anio, 1, 1)
    con_movimientos = (
        Movimiento.objects.filter(fecha__gte=enero, fecha__lt=date(anio + 1, 1, 1)).values("hogar_id").distinct()
    )
    ya_hechos = InformeMensual.objects.filter(tipo=InformeMensual.Tipo.ANUAL, mes=enero).values("hogar_id")
    pendientes = Hogar.objects.filter(pk__in=con_movimientos).exclude(pk__in=ya_hechos).values_list("pk", flat=True)
    for hogar_id in pendientes:
        generar_informe.delay(hogar_id, enero.isoformat(), tipo=InformeMensual.Tipo.ANUAL)
    return len(pendientes)


@shared_task(acks_late=True, autoretry_for=(OSError,), retry_backoff=60, max_retries=3)
def generar_informe(
    hogar_id: int, mes: str, usuario_id: int | None = None, enviar: bool = True, tipo: str = "mensual"
) -> int:
    usuario = get_user_model().objects.filter(pk=usuario_id).first() if usuario_id else None
    return services.generar(hogar_id, date.fromisoformat(mes), tipo=tipo, usuario=usuario, enviar=enviar).pk


@task(queue_name="emails")  # django.tasks: un email por destinatario, con reintento independiente
def enviar_informe(informe_id: int, usuario_id: int) -> None:
    informe = InformeMensual.objects.select_related("hogar").get(pk=informe_id)
    usuario = get_user_model().objects.get(pk=usuario_id)
    token = services.token_baja(usuario)
    with translation.override(usuario.idioma):
        if informe.es_anual:
            resumen = services.contexto_anual(informe.hogar, informe.mes.year)["resumen"]
            asunto = _("Tu informe anual de %(anio)s · %(hogar)s") % {
                "anio": informe.periodo,
                "hogar": informe.hogar.nombre,
            }
        else:
            resumen = dashboard.calcular(informe.hogar, informe.mes)
            asunto = _("Tu informe de %(mes)s · %(hogar)s") % {
                "mes": f"{informe.mes:%m/%Y}",
                "hogar": informe.hogar.nombre,
            }
        contexto = {
            "usuario": usuario,
            "informe": informe,
            "periodo": services.nombre_periodo(informe),
            "resumen": resumen,
            "enlace": f"/hogares/{informe.hogar_id}/informes",
            "frontend_url": settings.FRONTEND_URL,
            "enlace_baja": f"{settings.FRONTEND_URL}/baja-informes?token={token}",  # página con un botón
        }
        mensaje = EmailMultiAlternatives(
            subject=asunto,
            body=render_to_string("informes/email_informe.txt", contexto),
            to=[Address(display_name=usuario.get_full_name(), addr_spec=usuario.email)],  # módulo 22
            headers={
                # RFC 2369 + RFC 8058 (baja en un clic): el cliente de correo hace un POST a esta URL, sin
                # pasar por el navegador. Gmail y Yahoo la exigen a quien envía correo masivo desde 2024.
                "List-Unsubscribe": f"<{settings.FRONTEND_URL}/api/v1/informes/baja/{token}/>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        )
        mensaje.attach_alternative(render_to_string("informes/email_informe.html", contexto), "text/html")
    with informe.archivo.open("rb") as f:
        mensaje.attach(f"gastos-{informe.periodo}.pdf", f.read(), "application/pdf")
    mensaje.send()
