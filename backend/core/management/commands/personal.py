from django.contrib.auth.models import Group
from django.core.management import BaseCommand, CommandError
from django.db import transaction
from django.forms.models import model_to_dict

from core.auditoria import registrar
from core.grupos import GRUPOS
from core.models import RegistroAuditoria
from usuarios.models import Usuario


class Command(BaseCommand):
    help = "Da o quita acceso al backoffice (is_staff + grupo). Sin Django admin, el alta del personal es esto."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--grupo", default="Soporte", choices=sorted(GRUPOS))
        parser.add_argument("--quitar", action="store_true", help="retira el acceso y todos los grupos")

    @transaction.atomic
    def handle(self, email, grupo, quitar, **opciones):
        try:
            usuario = Usuario.objects.select_for_update().get(email__iexact=email)
        except Usuario.DoesNotExist:
            raise CommandError(
                f"No hay ningún usuario con el email {email}: que se registre primero en la app."
            ) from None
        antes = model_to_dict(usuario, fields=["is_staff", "groups"])

        usuario.is_staff = not quitar
        usuario.save(update_fields=["is_staff"])
        if quitar:
            usuario.groups.clear()
        else:
            usuario.groups.add(Group.objects.get(name=grupo))

        registrar(usuario, RegistroAuditoria.Accion.MODIFICAR, antes=antes)  # sin usuario: fue desde el servidor
        estado = "ya no es personal" if quitar else f"es personal ({grupo})"
        self.stdout.write(self.style.SUCCESS(f"{usuario.email} {estado}"))
