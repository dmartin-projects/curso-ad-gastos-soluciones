"""Módulo 82, ejercicio 1: lo que falta por probar de usuarios/api/views.py y usuarios/services.py."""

import re
from datetime import timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from django.core import mail
from django.utils import timezone

from conftest import UsuarioFactory
from usuarios.models import Usuario

pytestmark = pytest.mark.django_db
A = "/api/v1/auth/"


def enlace_del_email() -> dict:
    url = re.search(r"https?://\S+", mail.outbox[-1].body).group(0)
    return {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}  # {"uid": …, "token": …}


# ── Registro ──
def test_registro_con_el_email_de_una_cuenta_en_otras_mayusculas(api, django_capture_on_commit_callbacks):
    UsuarioFactory(email="ana@example.com")
    with django_capture_on_commit_callbacks(execute=True):
        r = api.post(A + "registro/", {"email": "ANA@Example.com", "nombre": "Ana"})
    assert r.status_code == 202  # la misma respuesta que con un email nuevo
    assert Usuario.objects.filter(email__iexact="ana@example.com").count() == 1
    assert (mail.outbox[-1].to, mail.outbox[-1].subject) == (["ana@example.com"], "Ya tienes una cuenta")


@pytest.mark.parametrize(
    "password, motivo",
    [("123", "corta"), ("password123", "común"), ("ana@example.com", "parecida al email"), ("12345678901", "numérica")],
)
def test_completar_registro_con_password_debil(api, django_capture_on_commit_callbacks, password, motivo):
    with django_capture_on_commit_callbacks(execute=True):
        api.post(A + "registro/", {"email": "ana@example.com", "nombre": "Ana"})
    r = api.post(A + "completar-registro/", enlace_del_email() | {"password": password})
    assert r.status_code == 400 and "password" in r.json()["errors"], motivo
    assert not Usuario.objects.get().is_active


def test_completar_registro_con_enlace_falso(api):
    assert api.post(A + "completar-registro/", {"uid": "MQ", "token": "falso"}).status_code == 400
    assert api.post(A + "completar-registro/", {"uid": "%%%", "token": "x"}).status_code == 400  # uid ilegible


# ── Restablecer la contraseña ──
@pytest.fixture
def con_enlace(api, django_capture_on_commit_callbacks):
    u = UsuarioFactory(email="luis@example.com")
    u.set_password("la-antigua-123")
    u.save()
    with django_capture_on_commit_callbacks(execute=True):
        r = api.post(A + "recuperar-password/", {"email": "LUIS@example.com"})
    assert r.status_code == 200
    return u, enlace_del_email()


def test_solicitar_no_revela_si_el_email_existe(api, django_capture_on_commit_callbacks):
    with django_capture_on_commit_callbacks(execute=True):
        r = api.post(A + "recuperar-password/", {"email": "nadie@example.com"})
    assert r.status_code == 200 and r.json()["detail"].startswith("Si el email existe")
    assert len(mail.outbox) == 0


def test_token_valido_cambia_la_password(api, con_enlace):
    u, enlace = con_enlace
    r = api.post(A + "recuperar-password/confirmar/", enlace | {"password": "la-nueva-larga-456"})
    assert r.status_code == 204
    u.refresh_from_db()
    assert u.check_password("la-nueva-larga-456")


def test_token_reutilizado_no_vale(api, con_enlace):
    _, enlace = con_enlace
    assert api.post(A + "recuperar-password/confirmar/", enlace | {"password": "la-nueva-larga-456"}).status_code == 204
    # el token incluye el hash de la contraseña: al cambiarla, el mismo enlace deja de servir
    r = api.post(A + "recuperar-password/confirmar/", enlace | {"password": "otra-mas-larga-789"})
    assert r.status_code == 400


def test_token_caducado(api, con_enlace, settings, time_machine):
    _, enlace = con_enlace
    # Un día de margen: el generador de tokens usa datetime.now() (hora local, sin zona) y time_machine
    # interpreta las fechas con zona en UTC; con el margen, la diferencia de 1-2 h no importa.
    time_machine.move_to(timezone.now() + timedelta(seconds=settings.PASSWORD_RESET_TIMEOUT) + timedelta(days=1))
    r = api.post(A + "recuperar-password/confirmar/", enlace | {"password": "la-nueva-larga-456"})
    assert r.status_code == 400 and "caducado" in r.json()["title"]


def test_password_nueva_debil_no_se_acepta(api, con_enlace):
    u, enlace = con_enlace
    r = api.post(A + "recuperar-password/confirmar/", enlace | {"password": "123"})
    assert r.status_code == 400
    u.refresh_from_db()
    assert u.check_password("la-antigua-123")  # y el enlace sigue valiendo para un segundo intento
    assert api.post(A + "recuperar-password/confirmar/", enlace | {"password": "ahora-si-larga-1"}).status_code == 204


def test_me_lee_y_edita_solo_lo_permitido(cliente):
    u = UsuarioFactory(nombre="Ana")
    c = cliente(u)
    assert c.get(A + "me/").json()["nombre"] == "Ana"
    r = c.patch(A + "me/", {"nombre": "Ana María", "email": "otro@example.com", "es_personal": True})
    assert r.status_code == 200 and r.json()["nombre"] == "Ana María"
    u.refresh_from_db()
    assert u.email != "otro@example.com" and not u.is_staff  # los read_only se ignoran


def test_cambiar_password_con_la_actual_mal(cliente):
    u = UsuarioFactory()
    u.set_password("la-de-siempre-1")
    u.save()
    r = cliente(u).post(A + "cambiar-password/", {"actual": "no-es-esta", "nueva": "otra-larga-nueva-2"})
    assert r.status_code == 400 and "actual" in r.json()["errors"]
