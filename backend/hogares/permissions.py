from functools import cached_property

from rest_framework.exceptions import NotFound
from rest_framework.permissions import BasePermission

from .models import Membresia

NIVEL = {Membresia.Rol.LECTOR: 0, Membresia.Rol.MIEMBRO: 1, Membresia.Rol.ADMIN: 2}

ROLES_POR_METODO = {
    "GET": Membresia.Rol.LECTOR,
    "HEAD": Membresia.Rol.LECTOR,
    "OPTIONS": Membresia.Rol.LECTOR,
    "POST": Membresia.Rol.MIEMBRO,
    "PUT": Membresia.Rol.MIEMBRO,
    "PATCH": Membresia.Rol.MIEMBRO,
    "DELETE": Membresia.Rol.MIEMBRO,
}


class HogarDesdeUrlMixin:
    """Vistas anidadas en /hogares/<hogar_pk>/…

    Resuelve el hogar de la URL y la membresía del usuario. Si el usuario no pertenece
    al hogar, responde 404 (ni siquiera revela que el hogar existe).
    """

    hogar_url_kwarg = "hogar_pk"

    @cached_property
    def membresia(self) -> Membresia:
        m = (
            Membresia.objects.select_related("hogar")
            .filter(hogar_id=self.kwargs[self.hogar_url_kwarg], usuario=self.request.user)
            .first()
        )
        if m is None:
            raise NotFound()
        return m

    @property
    def hogar(self):
        return self.membresia.hogar

    def es_esquema(self) -> bool:
        """True mientras drf-spectacular genera el esquema (no hay usuario real)."""
        return getattr(self, "swagger_fake_view", False)


class RolEnHogar(BasePermission):
    """Exige un rol mínimo según el método HTTP (o según `roles_por_accion` de la vista)."""

    message = "Tu rol en este hogar no permite esta acción."

    def has_permission(self, request, view):
        if getattr(view, "swagger_fake_view", False):
            return True
        requerido = getattr(view, "roles_por_accion", {}).get(getattr(view, "action", None)) or getattr(
            view, "roles_por_metodo", ROLES_POR_METODO
        ).get(request.method, Membresia.Rol.ADMIN)
        return NIVEL[view.membresia.rol] >= NIVEL[requerido]
