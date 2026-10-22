import pytest
from django.core import mail

from hogares.models import Invitacion, Membresia

pytestmark = pytest.mark.django_db
URL = "/api/v1/hogares/"


def test_crear_hogar_me_hace_admin(cliente, django_capture_on_commit_callbacks):
    from conftest import UsuarioFactory

    u = UsuarioFactory()
    r = cliente(u).post(URL, {"nombre": "Piso Lavapiés"})
    assert r.status_code == 201, r.json()
    assert r.json()["mi_rol"] == "admin" and r.json()["num_miembros"] == 1


@pytest.mark.parametrize("rol, esperado", [("admin", 200), ("miembro", 200), ("lector", 200), ("ajeno", 404)])
def test_ver_miembros(cliente, hogar_con_roles, rol, esperado):
    hogar, roles = hogar_con_roles
    assert cliente(roles[rol]).get(f"{URL}{hogar.pk}/miembros/").status_code == esperado


@pytest.mark.parametrize("rol, esperado", [("admin", 201), ("miembro", 403), ("lector", 403), ("ajeno", 404)])
def test_invitar_solo_admin(cliente, hogar_con_roles, rol, esperado, django_capture_on_commit_callbacks):
    hogar, roles = hogar_con_roles
    with django_capture_on_commit_callbacks(execute=True):
        r = cliente(roles[rol]).post(
            f"{URL}{hogar.pk}/miembros/invitar/", {"email": "Nuevo@Example.com", "rol": "lector"}
        )
    assert r.status_code == esperado, r.json()
    if esperado == 201:
        assert len(mail.outbox) == 1 and mail.outbox[0].to == ["nuevo@example.com"]


def test_aceptar_invitacion(cliente, hogar_con_roles, django_capture_on_commit_callbacks):
    from conftest import UsuarioFactory

    hogar, roles = hogar_con_roles
    with django_capture_on_commit_callbacks(execute=True):
        cliente(roles["admin"]).post(
            f"{URL}{hogar.pk}/miembros/invitar/", {"email": "nuevo@example.com", "rol": "lector"}
        )
    token = Invitacion.objects.get(email="nuevo@example.com").token
    otro = UsuarioFactory(email="otro@example.com")
    assert cliente(otro).post(f"/api/v1/invitaciones/{token}/aceptar/").json()["type"] == "invitacion_no_valida"
    nuevo = UsuarioFactory(email="nuevo@example.com")
    r = cliente(nuevo).post(f"/api/v1/invitaciones/{token}/aceptar/")
    assert r.status_code == 200 and r.json()["rol"] == "lector"
    assert cliente(nuevo).post(f"/api/v1/invitaciones/{token}/aceptar/").status_code == 400  # ya usada


def test_no_se_puede_quitar_el_ultimo_admin(cliente, hogar_con_roles):
    hogar, roles = hogar_con_roles
    m = Membresia.objects.get(hogar=hogar, usuario=roles["admin"])
    r = cliente(roles["admin"]).patch(f"{URL}{hogar.pk}/miembros/{m.pk}/", {"rol": "miembro"})
    assert r.status_code == 409 and r.json()["type"] == "ultimo_administrador"


def test_el_unico_admin_no_puede_expulsarse(cliente, hogar_con_roles):
    hogar, roles = hogar_con_roles
    m = Membresia.objects.get(hogar=hogar, usuario=roles["admin"])
    r = cliente(roles["admin"]).delete(f"{URL}{hogar.pk}/miembros/{m.pk}/")
    assert r.status_code == 409 and r.json()["type"] == "ultimo_administrador"
    assert Membresia.objects.filter(pk=m.pk).exists()


def test_solo_admin_edita_el_hogar(cliente, hogar_con_roles):
    hogar, roles = hogar_con_roles
    assert cliente(roles["miembro"]).patch(f"{URL}{hogar.pk}/", {"nombre": "x"}).status_code == 403
    assert cliente(roles["admin"]).patch(f"{URL}{hogar.pk}/", {"nombre": "x"}).status_code == 200
    assert cliente(roles["ajeno"]).get(f"{URL}{hogar.pk}/").status_code == 404
