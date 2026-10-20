import pytest

from hogares.models import Invitacion, Membresia

pytestmark = pytest.mark.django_db
URL = "/api/v1/hogares/"


def _m(hogar, usuario):
    return Membresia.objects.get(hogar=hogar, usuario=usuario)


@pytest.mark.parametrize("rol", ["miembro", "lector"])
def test_puedo_salir_yo_mismo(cliente, hogar_con_roles, rol):
    hogar, roles = hogar_con_roles
    m = _m(hogar, roles[rol])
    assert cliente(roles[rol]).delete(f"{URL}{hogar.pk}/miembros/{m.pk}/").status_code == 204
    assert not Membresia.objects.filter(pk=m.pk).exists()
    # Ya no pertenezco: el hogar deja de existir para mí.
    assert cliente(roles[rol]).get(f"{URL}{hogar.pk}/").status_code == 404


def test_un_miembro_no_puede_expulsar_a_otro(cliente, hogar_con_roles):
    hogar, roles = hogar_con_roles
    lector = _m(hogar, roles["lector"])
    r = cliente(roles["miembro"]).delete(f"{URL}{hogar.pk}/miembros/{lector.pk}/")
    assert r.status_code == 403
    assert Membresia.objects.filter(pk=lector.pk).exists()


def test_el_admin_si_puede_expulsar(cliente, hogar_con_roles):
    hogar, roles = hogar_con_roles
    lector = _m(hogar, roles["lector"])
    assert cliente(roles["admin"]).delete(f"{URL}{hogar.pk}/miembros/{lector.pk}/").status_code == 204


def test_el_ultimo_admin_no_puede_salir(cliente, hogar_con_roles):
    hogar, roles = hogar_con_roles
    m = _m(hogar, roles["admin"])
    r = cliente(roles["admin"]).delete(f"{URL}{hogar.pk}/miembros/{m.pk}/")
    assert r.status_code == 409 and r.json()["type"] == "ultimo_administrador"
    # Si nombra antes a otro admin, ya puede irse.
    otro = _m(hogar, roles["miembro"])
    cliente(roles["admin"]).patch(f"{URL}{hogar.pk}/miembros/{otro.pk}/", {"rol": "admin"})
    assert cliente(roles["admin"]).delete(f"{URL}{hogar.pk}/miembros/{m.pk}/").status_code == 204


def test_ajeno_no_ve_ni_borra(cliente, hogar_con_roles):
    hogar, roles = hogar_con_roles
    m = _m(hogar, roles["lector"])
    assert cliente(roles["ajeno"]).delete(f"{URL}{hogar.pk}/miembros/{m.pk}/").status_code == 404


@pytest.fixture
def invitacion(hogar_con_roles):
    hogar, roles = hogar_con_roles
    return Invitacion.objects.create(hogar=hogar, email="pendiente@example.com", invitado_por=roles["admin"])


@pytest.mark.parametrize("rol, esperado", [("admin", 204), ("miembro", 403), ("lector", 403), ("ajeno", 404)])
def test_anular_invitacion_solo_admin(cliente, hogar_con_roles, invitacion, rol, esperado):
    hogar, roles = hogar_con_roles
    r = cliente(roles[rol]).delete(f"{URL}{hogar.pk}/invitaciones/{invitacion.pk}/")
    assert r.status_code == esperado
    assert Invitacion.objects.filter(pk=invitacion.pk).exists() == (esperado != 204)


def test_invitacion_anulada_ya_no_se_puede_aceptar(cliente, hogar_con_roles, invitacion):
    from conftest import UsuarioFactory

    hogar, roles = hogar_con_roles
    cliente(roles["admin"]).delete(f"{URL}{hogar.pk}/invitaciones/{invitacion.pk}/")
    invitado = UsuarioFactory(email="pendiente@example.com")
    r = cliente(invitado).post(f"/api/v1/invitaciones/{invitacion.token}/aceptar/")
    assert r.status_code == 400 and r.json()["type"] == "invitacion_no_valida"


def test_no_se_anulan_aceptadas_ni_de_otro_hogar(cliente, hogar_con_roles, invitacion):
    from django.utils import timezone

    from conftest import HogarFactory

    hogar, roles = hogar_con_roles
    invitacion.aceptada = timezone.now()
    invitacion.save()
    ajena = Invitacion.objects.create(hogar=HogarFactory(), email="x@example.com")
    admin = cliente(roles["admin"])
    assert admin.delete(f"{URL}{hogar.pk}/invitaciones/{invitacion.pk}/").status_code == 404
    assert admin.delete(f"{URL}{hogar.pk}/invitaciones/{ajena.pk}/").status_code == 404
    assert admin.get(f"{URL}{hogar.pk}/invitaciones/").json() == []
