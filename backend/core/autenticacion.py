import logging

from drf_spectacular.contrib.rest_framework_simplejwt import SimpleJWTScheme
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import SAFE_METHODS
from rest_framework_simplejwt.authentication import JWTAuthentication

logger = logging.getLogger("gastos.suplantacion")


class JWTConSuplantacion(JWTAuthentication):
    """JWT normal + tokens de suplantación (módulo 79): solo lectura y cada petición queda en el log.

    Va en la AUTENTICACIÓN y no en un permiso: casi todas las vistas definen sus propios
    `permission_classes`, y un permiso por defecto se perdería en ellas; la autenticación es común.
    """

    def authenticate(self, request):
        resultado = super().authenticate(request)
        if resultado is None:
            return None
        usuario, token = resultado
        if suplantador := token.get("suplantado_por"):
            logger.info(
                "Suplantación: personal %s como usuario %s → %s %s",
                suplantador,
                usuario.pk,
                request.method,
                request.path,
                extra={"suplantador": suplantador, "usuario_id": usuario.pk},
            )
            if request.method not in SAFE_METHODS:
                raise PermissionDenied("Sesión de suplantación: solo lectura.")
        return usuario, token


class EsquemaJWTConSuplantacion(SimpleJWTScheme):
    """drf-spectacular reconoce JWTAuthentication, pero no a sus subclases: se le dice que es el mismo esquema."""

    target_class = JWTConSuplantacion
