from django.conf import settings
from django.core.mail import send_mail
from django.tasks import task
from django.utils.translation import gettext as _

from .models import Invitacion


@task(queue_name="emails")
def enviar_invitacion(invitacion_id: int) -> None:
    inv = Invitacion.objects.select_related("hogar", "invitado_por").get(pk=invitacion_id)
    enlace = f"{settings.FRONTEND_URL}/invitaciones/{inv.token}"
    send_mail(
        _("Te han invitado a «%(hogar)s»") % {"hogar": inv.hogar.nombre},
        _("%(quien)s te invita a compartir las cuentas de «%(hogar)s». Acepta aquí: %(enlace)s")
        % {
            "quien": inv.invitado_por.get_full_name() if inv.invitado_por else "",
            "hogar": inv.hogar.nombre,
            "enlace": enlace,
        },
        None,
        [inv.email],
    )
