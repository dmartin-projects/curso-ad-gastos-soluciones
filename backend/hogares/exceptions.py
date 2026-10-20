from django.utils.translation import gettext_lazy as _

from core.exceptions import ErrorDeDominio


class InvitacionNoValida(ErrorDeDominio):
    codigo = "invitacion_no_valida"
    status = 400
    mensaje = _("La invitación no existe, ha caducado o ya se ha usado.")


class YaEsMiembro(ErrorDeDominio):
    codigo = "ya_es_miembro"
    mensaje = _("Ya perteneces a este hogar.")


class UltimoAdministrador(ErrorDeDominio):
    codigo = "ultimo_administrador"
    mensaje = _("Un hogar necesita al menos un administrador.")
