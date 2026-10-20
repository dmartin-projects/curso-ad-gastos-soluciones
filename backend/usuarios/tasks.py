from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.tasks import task
from django.utils import translation
from django.utils.translation import gettext as _


@task(queue_name="emails")
def enviar_email_verificacion(usuario_id: int, enlace: str) -> None:
    usuario = get_user_model().objects.get(pk=usuario_id)
    with translation.override(usuario.idioma):
        send_mail(
            _("Confirma tu email"),
            _("Abre este enlace para activar tu cuenta: %(enlace)s") % {"enlace": enlace},
            None,
            [usuario.email],
        )


@task(queue_name="emails")
def enviar_email_recuperacion(usuario_id: int, enlace: str) -> None:
    usuario = get_user_model().objects.get(pk=usuario_id)
    with translation.override(usuario.idioma):
        send_mail(
            _("Recupera tu contraseña"),
            _("Abre este enlace para elegir una contraseña nueva: %(enlace)s") % {"enlace": enlace},
            None,
            [usuario.email],
        )
