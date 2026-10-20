import logging
from datetime import date
from email.headerregistry import Address

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


@shared_task(ignore_result=True)
def generar_informes_mensuales() -> int:
    """Coordinadora (Celery Beat, día 1 a las 7:00): encola UNA tarea por hogar, no un bucle de horas (módulo 26)."""
    mes = dashboard.mes_anterior(timezone.localdate().replace(day=1))  # TIME_ZONE del proyecto (Madrid)
    con_movimientos = Movimiento.objects.del_mes(mes).values("hogar_id").distinct()
    pendientes = (
        Hogar.objects.filter(pk__in=con_movimientos)
        .exclude(informes__mes=mes)  # si Beat se reinicia y la lanza dos veces, no se repite nada
        .values_list("pk", flat=True)
    )
    for hogar_id in pendientes:
        generar_informe.delay(hogar_id, mes.isoformat())
    logger.info("Informes de %s encolados: %s", f"{mes:%Y-%m}", len(pendientes))
    return len(pendientes)


@shared_task(acks_late=True, autoretry_for=(OSError,), retry_backoff=60, max_retries=3)
def generar_informe(hogar_id: int, mes: str, usuario_id: int | None = None, enviar: bool = True) -> int:
    usuario = get_user_model().objects.filter(pk=usuario_id).first() if usuario_id else None
    return services.generar(hogar_id, date.fromisoformat(mes), usuario=usuario, enviar=enviar).pk


@task(queue_name="emails")  # django.tasks: un email por destinatario, con reintento independiente
def enviar_informe(informe_id: int, usuario_id: int) -> None:
    informe = InformeMensual.objects.select_related("hogar").get(pk=informe_id)
    usuario = get_user_model().objects.get(pk=usuario_id)
    with translation.override(usuario.idioma):
        contexto = {
            "usuario": usuario,
            "informe": informe,
            "resumen": dashboard.calcular(informe.hogar, informe.mes),
            "enlace": f"/hogares/{informe.hogar_id}/informes",
            "frontend_url": settings.FRONTEND_URL,
        }
        mensaje = EmailMultiAlternatives(
            subject=_("Tu informe de %(mes)s · %(hogar)s")
            % {"mes": f"{informe.mes:%m/%Y}", "hogar": informe.hogar.nombre},
            body=render_to_string("informes/email_informe.txt", contexto),
            to=[Address(display_name=usuario.get_full_name(), addr_spec=usuario.email)],  # módulo 22
        )
        mensaje.attach_alternative(render_to_string("informes/email_informe.html", contexto), "text/html")
    with informe.archivo.open("rb") as f:
        mensaje.attach(f"gastos-{informe.mes:%Y-%m}.pdf", f.read(), "application/pdf")
    mensaje.send()
