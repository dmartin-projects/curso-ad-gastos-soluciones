from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.tasks import task
from django.utils import translation
from django.utils.translation import gettext as _


@task(queue_name="emails")
def enviar_email_completar_registro(usuario_id: int, enlace: str) -> None:
    usuario = get_user_model().objects.get(pk=usuario_id)
    with translation.override(usuario.idioma):
        send_mail(
            _("Completa tu registro"),
            _(
                "Hola %(nombre)s:\n\nPara completar tu registro, elige tu contraseña en este enlace:\n%(enlace)s\n\n"
                "Si no te has registrado tú, ignora este mensaje: sin ese paso la cuenta no se activa."
            )
            % {"nombre": usuario.nombre or usuario.email, "enlace": enlace},
            None,
            [usuario.email],
        )


@task(queue_name="emails")
def enviar_email_cuenta_existente(usuario_id: int, enlace: str) -> None:
    usuario = get_user_model().objects.get(pk=usuario_id)
    with translation.override(usuario.idioma):
        send_mail(
            _("Ya tienes una cuenta"),
            _(
                "Hola %(nombre)s:\n\nAlguien ha intentado registrarse con este email, pero ya tienes una cuenta. "
                "Si no recuerdas la contraseña, elige una nueva aquí:\n%(enlace)s\n\n"
                "Si no has sido tú, ignora este mensaje: tu cuenta no ha cambiado."
            )
            % {"nombre": usuario.nombre or usuario.email, "enlace": enlace},
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
