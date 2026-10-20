from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.tasks import task
from django.utils import translation
from django.utils.translation import gettext as _

from .models import Notificacion
from .services import emitir_a_hogar


@task(queue_name="emails")  # django.tasks (módulo 26): un email sencillo no necesita Celery
def enviar_email_notificacion(notificacion_id: int) -> None:
    n = Notificacion.objects.select_related("usuario").get(pk=notificacion_id)
    with translation.override(n.usuario.idioma):
        cuerpo = f"{n.mensaje}\n\n{_('Ábrelo en la app')}: {settings.FRONTEND_URL}{n.enlace}"
        send_mail(n.titulo, cuerpo, None, [n.usuario.email])


@shared_task(ignore_result=True)
def emitir_evento_hogar(hogar_id: int, evento: str) -> None:
    """Se encola con `agrupar` (debounce): un aviso por ventana, aunque cambien 500 movimientos."""
    emitir_a_hogar(hogar_id, evento)
