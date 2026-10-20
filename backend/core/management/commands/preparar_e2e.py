import psycopg
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.management import BaseCommand, CommandError, call_command
from psycopg import sql

from usuarios.models import Usuario


class Command(BaseCommand):
    help = "Deja la BD de pruebas E2E en un estado conocido (solo con config.settings.e2e)."

    # Los checks del sistema se conectan a la BD (GeneratedField pregunta qué admite PostgreSQL) y con
    # --crear-bd todavía no existe: se omiten aquí; migrate (call_command) no los necesita.
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--crear-bd", action="store_true", help="Crea la BD si no existe y aplica migraciones")

    def handle(self, *args, crear_bd=False, **opciones):
        if settings.ROOT_URLCONF != "config.urls_e2e":
            raise CommandError("Solo con DJANGO_SETTINGS_MODULE=config.settings.e2e: borra todos los datos.")
        if crear_bd:  # módulo 82: una BD por worker de Playwright (gastos_e2e_0, gastos_e2e_1…)
            self._crear_bd()
            call_command("migrate", interactive=False, verbosity=0)
        call_command("flush", interactive=False, verbosity=0)  # vacía las tablas; post_migrate recrea los grupos
        call_command("seed", movimientos=300, verbosity=0)  # demo@example.com / demo12345-demo
        soporte = Usuario.objects.create_user("soporte@example.com", "soporte12345", nombre="Soporte", is_staff=True)
        soporte.groups.add(Group.objects.get(name="Soporte"))
        self.stdout.write(self.style.SUCCESS("BD E2E preparada"))

    def _crear_bd(self):
        bd = settings.DATABASES["default"]
        # se conecta a la BD "postgres" (siempre existe) para crear la de este worker
        with psycopg.connect(
            dbname="postgres",
            user=bd["USER"],
            password=bd["PASSWORD"],
            host=bd["HOST"],
            port=bd["PORT"] or 5432,
            autocommit=True,  # CREATE DATABASE no puede ir dentro de una transacción
        ) as conexion:
            existe = conexion.execute("SELECT 1 FROM pg_database WHERE datname = %s", [bd["NAME"]]).fetchone()
            if not existe:
                conexion.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(bd["NAME"])))
