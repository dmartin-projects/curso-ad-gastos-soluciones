from django.apps import AppConfig


class NotificacionesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "notificaciones"

    def ready(self):
        from . import receivers  # noqa: F401  (registra los receptores, módulo 15)
