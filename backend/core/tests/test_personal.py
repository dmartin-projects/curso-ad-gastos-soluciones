import pytest
from django.core.management import CommandError, call_command

from conftest import UsuarioFactory
from core.models import RegistroAuditoria

pytestmark = pytest.mark.django_db


def test_dar_y_quitar_acceso_al_backoffice(api):
    usuario = UsuarioFactory(email="ana@example.com")
    api.force_authenticate(usuario)
    assert api.get("/api/v1/backoffice/resumen/").status_code == 404  # para un usuario normal no existe

    call_command("personal", "ANA@example.com")  # el email, sin distinguir mayúsculas
    usuario.refresh_from_db()
    assert usuario.is_staff and list(usuario.groups.values_list("name", flat=True)) == ["Soporte"]
    assert api.get("/api/v1/backoffice/resumen/").status_code == 200

    call_command("personal", "ana@example.com", "--quitar")
    usuario.refresh_from_db()
    assert not usuario.is_staff and not usuario.groups.exists()
    cambios = [r.cambios["is_staff"] for r in RegistroAuditoria.objects.order_by("fecha")]
    assert cambios == [["False", "True"], ["True", "False"]]


def test_el_usuario_tiene_que_existir():
    with pytest.raises(CommandError, match="que se registre primero"):
        call_command("personal", "nadie@example.com")
