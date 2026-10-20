from django.utils.translation import gettext_lazy as _

from core.exceptions import ErrorDeDominio


class EstadoNoPermitido(ErrorDeDominio):
    codigo = "importacion_estado_no_permitido"
    mensaje = _("La importación no está en un estado que permita esta operación.")
