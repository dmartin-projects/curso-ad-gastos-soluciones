from django.utils.translation import gettext_lazy as _

from core.exceptions import ErrorDeDominio


class CuentaConMovimientos(ErrorDeDominio):
    codigo = "cuenta_con_movimientos"
    mensaje = _("La cuenta tiene movimientos: desactívala en lugar de borrarla.")
