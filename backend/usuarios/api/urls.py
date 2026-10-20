# usuarios/api/urls.py
from django.urls import path

from . import (
    auth,
    esquema,  # noqa: F401  (registra la documentación OpenAPI)
    views,
)

urlpatterns = [
    path("login/", auth.Login.as_view(), name="auth-login"),
    path("refresh/", auth.Refresh.as_view(), name="auth-refresh"),
    path("logout/", auth.Logout.as_view(), name="auth-logout"),
    path("registro/", views.Registro.as_view(), name="auth-registro"),
    path("verificar-email/", views.VerificarEmail.as_view(), name="auth-verificar-email"),
    path("me/", views.Yo.as_view(), name="auth-me"),
    path("cambiar-password/", views.CambiarPassword.as_view(), name="auth-cambiar-password"),
    path("recuperar-password/", views.SolicitarRecuperacion.as_view(), name="auth-recuperar"),
    path("recuperar-password/confirmar/", views.ConfirmarRecuperacion.as_view(), name="auth-recuperar-confirmar"),
]
