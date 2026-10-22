from django.utils.translation import gettext_lazy as _

from core.exceptions import ErrorDeDominio


class EnlaceNoValido(ErrorDeDominio):
    codigo = "enlace_no_valido"
    status = 400
    mensaje = _("Enlace no válido o caducado.")
