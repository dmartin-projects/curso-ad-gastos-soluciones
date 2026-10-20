from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management import BaseCommand, CommandError, call_command

from usuarios.models import Usuario


class Command(BaseCommand):
    help = "Deja la BD de pruebas E2E en un estado conocido (solo con config.settings.e2e)."

    def handle(self, *args, **opciones):
        if settings.ROOT_URLCONF != "config.urls_e2e":
            raise CommandError("Solo con DJANGO_SETTINGS_MODULE=config.settings.e2e: borra todos los datos.")
        call_command("flush", interactive=False, verbosity=0)  # vacía las tablas; post_migrate recrea los grupos
        call_command("seed", movimientos=300, verbosity=0)  # demo@example.com / demo12345-demo
        soporte = Usuario.objects.create_user("soporte@example.com", "soporte12345", nombre="Soporte", is_staff=True)
        soporte.groups.add(Group.objects.get(name="Soporte"))
        self.stdout.write(self.style.SUCCESS("BD E2E preparada"))
