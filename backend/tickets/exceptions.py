from django.utils.translation import gettext_lazy as _

from core.exceptions import ErrorDeDominio


class EstadoNoPermitido(ErrorDeDominio):
    codigo = "ticket_estado_no_permitido"
    mensaje = _("El ticket no está en un estado que permita esta operación.")
