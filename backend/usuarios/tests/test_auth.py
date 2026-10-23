import re

import pytest
from django.core import mail
from django.core.cache import cache
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

from usuarios.models import Usuario

pytestmark = pytest.mark.django_db
A = "/api/v1/auth/"


@pytest.fixture(autouse=True)
def limpiar_cache():
    cache.clear()


def enlace_del_email() -> tuple[str, str]:
    return re.search(r"uid=(\S+)&token=(\S+)", mail.outbox[-1].body).groups()


@pytest.fixture
def registrar(django_capture_on_commit_callbacks):
    def registrar(email, **datos):
        with django_capture_on_commit_callbacks(execute=True):
            return APIClient().post(A + "registro/", {"email": email, **datos})

    return registrar


def completar(uid, token, password):
    return APIClient().post(A + "completar-registro/", {"uid": uid, "token": token, "password": password})


def entrar(email, password):
    return APIClient().post(A + "login/", {"email": email, "password": password})


def test_registro_completar_login_refresh_logout(registrar):
    r = registrar("Ana@Example.com", nombre="Ana", password="la-ignora-77")  # sin contraseña: se ignora
    assert r.status_code == 202, r.json()
    ana = Usuario.objects.get(email="ana@example.com")  # normalizado
    assert not ana.is_active and not ana.has_usable_password()
    assert entrar("ana@example.com", "la-ignora-77").status_code == 401
    assert mail.outbox[-1].subject == "Completa tu registro"
    assert "http://localhost:4200/completar-registro?uid=" in mail.outbox[-1].body
    uid, token = enlace_del_email()
    assert completar(uid, token, "una-clave-muy-larga-77").status_code == 204
    assert completar(uid, token, "otra-clave-muy-larga").status_code == 400  # de un solo uso
    c = APIClient()
    r = c.post(A + "login/", {"email": "ana@example.com", "password": "una-clave-muy-larga-77"})
    assert r.status_code == 200 and "access" in r.json() and r.cookies["refresh"]["httponly"]
    c2 = APIClient()
    c2.credentials(HTTP_AUTHORIZATION="Bearer " + r.json()["access"])
    assert c2.get(A + "me/").json()["email"] == "ana@example.com"
    assert c.post(A + "refresh/").status_code == 200
    assert c.post(A + "logout/").status_code == 204
    assert c.post(A + "refresh/").status_code == 401


def test_registro_misma_respuesta_para_email_nuevo_pendiente_o_con_cuenta(registrar):
    from conftest import UsuarioFactory

    UsuarioFactory(email="ana@example.com")
    nuevo = registrar("luis@example.com")
    pendiente = registrar("luis@example.com")
    con_cuenta = registrar("ana@example.com")
    assert nuevo.status_code == pendiente.status_code == con_cuenta.status_code == 202
    assert nuevo.json() == pendiente.json() == con_cuenta.json()
    assert [(m.to, m.subject) for m in mail.outbox] == [
        (["luis@example.com"], "Completa tu registro"),
        (["luis@example.com"], "Completa tu registro"),  # el mismo enlace, otra vez
        (["ana@example.com"], "Ya tienes una cuenta"),  # se lo decimos a Ana, no a quien rellena el formulario
    ]
    assert "http://localhost:4200/nueva-password?uid=" in mail.outbox[-1].body
    assert entrar("ana@example.com", "clave-segura-123").status_code == 200  # su cuenta no ha cambiado


def test_registrar_un_email_ajeno_no_da_acceso(registrar):
    # Alguien registra el email de Eva antes que ella, con una contraseña que conoce.
    registrar("eva@example.com", password="clave-del-otro-123")
    assert entrar("eva@example.com", "clave-del-otro-123").status_code == 401
    # Solo quien lee el buzón de Eva puede elegir la contraseña; y será la de Eva.
    uid, token = enlace_del_email()
    assert completar(uid, token, "clave-de-eva-456").status_code == 204
    assert entrar("eva@example.com", "clave-de-eva-456").status_code == 200
    assert entrar("eva@example.com", "clave-del-otro-123").status_code == 401


def test_completar_valida_la_password_sin_gastar_el_enlace(registrar):
    registrar("luisgarcia@example.com", nombre="Luis")
    uid, token = enlace_del_email()
    r = completar(uid, token, "luisgarcia")
    assert r.status_code == 400 and set(r.json()["errors"]) == {"password"}  # demasiado parecida al email
    assert completar(uid, token, "una-clave-muy-larga-77").status_code == 204  # el enlace sigue valiendo


def test_el_enlace_de_otro_usuario_no_vale(registrar):
    registrar("luis@example.com")
    uid_luis, _ = enlace_del_email()
    registrar("eva@example.com")
    _, token_eva = enlace_del_email()
    assert completar(uid_luis, token_eva, "una-clave-muy-larga-77").status_code == 400


def test_recuperar_con_el_registro_pendiente_envia_el_de_completar(registrar, django_capture_on_commit_callbacks):
    registrar("luis@example.com")
    with django_capture_on_commit_callbacks(execute=True):
        APIClient().post(A + "recuperar-password/", {"email": "luis@example.com"})
    assert len(mail.outbox) == 2 and mail.outbox[-1].subject == "Completa tu registro"
    uid, token = enlace_del_email()
    datos = {"uid": uid, "token": token, "password": "una-clave-muy-larga-77"}
    assert APIClient().post(A + "recuperar-password/confirmar/", datos).status_code == 400  # no tiene qué recuperar
    assert completar(uid, token, "una-clave-muy-larga-77").status_code == 204


def test_completar_no_vale_para_una_cuenta_activa(django_capture_on_commit_callbacks):
    from conftest import UsuarioFactory

    UsuarioFactory(email="ana@example.com")
    with django_capture_on_commit_callbacks(execute=True):
        APIClient().post(A + "recuperar-password/", {"email": "ana@example.com"})
    uid, token = enlace_del_email()  # un enlace válido… de recuperar la contraseña
    assert completar(uid, token, "una-clave-muy-larga-77").status_code == 400


def test_cuenta_desactivada_no_recibe_enlaces(registrar, django_capture_on_commit_callbacks):
    from conftest import UsuarioFactory

    UsuarioFactory(email="ana@example.com", is_active=False)  # la desactivó soporte: nada la reactiva desde fuera
    assert registrar("ana@example.com").status_code == 202
    with django_capture_on_commit_callbacks(execute=True):
        APIClient().post(A + "recuperar-password/", {"email": "ana@example.com"})
    assert mail.outbox == []


def test_cambiar_password_cierra_otras_sesiones():
    from conftest import UsuarioFactory

    u = UsuarioFactory()
    c = APIClient()
    access = c.post(A + "login/", {"email": u.email, "password": "clave-segura-123"}).json()["access"]
    a = APIClient()
    a.credentials(HTTP_AUTHORIZATION="Bearer " + access)
    assert (
        a.post(A + "cambiar-password/", {"actual": "clave-segura-123", "nueva": "otra-clave-larga-99"}).status_code
        == 204
    )
    assert c.post(A + "refresh/").status_code == 401


def test_el_email_no_distingue_mayusculas():
    from conftest import UsuarioFactory

    UsuarioFactory(email="ana@example.com")
    r = APIClient().post(A + "login/", {"email": "ANA@Example.com", "password": "clave-segura-123"})
    assert r.status_code == 200 and "access" in r.json()  # get_by_natural_key del manager
    with pytest.raises(IntegrityError), transaction.atomic():  # y la BD no admite otra "Ana@…"
        Usuario.objects.create_user("Ana@Example.com", "otra-clave-larga-99")


def test_enlaces_y_contrasenas_con_el_formato_de_error(api):
    from conftest import UsuarioFactory
    from usuarios.services import generar_enlace

    falso = {"uid": "MQ", "token": "falso"}
    for ruta in ("completar-registro/", "recuperar-password/confirmar/"):
        r = api.post(A + ruta, falso | {"password": "una-clave-muy-larga-77"})
        assert r.status_code == 400 and r.json()["type"] == "enlace_no_valido"
        assert r.json()["title"] == "Enlace no válido o caducado."
    enlace = generar_enlace(UsuarioFactory(), "nueva-password")
    uid, token = re.search(r"uid=(\S+)&token=(\S+)", enlace).groups()
    r = api.post(A + "recuperar-password/confirmar/", {"uid": uid, "token": token, "password": "123"})
    assert r.status_code == 400 and set(r.json()["errors"]) == {"password"}  # todos los motivos, en su campo
