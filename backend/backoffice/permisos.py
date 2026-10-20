from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission


class EsPersonal(BasePermission):
    """Solo personal de la empresa (is_staff). Un usuario normal no sabe ni que existe: 404, no 403."""

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False  # → 401
        if not request.user.is_staff:
            raise NotFound()
        return True


class PermisosPorAccion(BasePermission):
    """Permisos de modelo de Django (los del grupo Soporte, módulo 14) por acción de la vista.

    Cierra por defecto: una acción que no aparezca en `permisos_por_accion` no se puede usar.
    """

    message = "Tu usuario de personal no tiene permiso para esta acción."

    def has_permission(self, request, view):
        requeridos = getattr(view, "permisos_por_accion", {}).get(getattr(view, "action", None))
        if requeridos is None:
            return False
        return request.user.has_perms(requeridos)
