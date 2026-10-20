from django.urls import include, path

urlpatterns = [
    path("auth/", include("usuarios.api.urls")),
    path("", include("hogares.api.urls")),
    path("", include("finanzas.api.urls")),
    path("", include("tickets.api.urls")),
    path("", include("importaciones.api.urls")),
    path("", include("notificaciones.api.urls")),
    path("", include("informes.api.urls")),
    path("backoffice/", include("backoffice.api.urls")),
]
