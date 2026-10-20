from django.apps import AppConfig
from django.db.models.signals import post_migrate


class CoreConfig(AppConfig):
    name = "core"

    def ready(self):
        from .grupos import crear_grupos

        # Una data migration no sirve: en una BD nueva los permisos se crean DESPUÉS de las migraciones
        post_migrate.connect(crear_grupos, sender=self, dispatch_uid="core_crear_grupos")
