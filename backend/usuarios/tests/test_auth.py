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


def test_registro_verificacion_login_refresh_logout(django_capture_on_commit_callbacks):
    c = APIClient()
    with django_capture_on_commit_callbacks(execute=True):
        r = c.post(A + "registro/", {"email": "Ana@Example.com", "nombre": "Ana", "password": "una-clave-muy-larga-77"})
    assert r.status_code == 201, r.json()
    assert c.post(A + "login/", {"email": "ana@example.com", "password": "una-clave-muy-larga-77"}).status_code == 401
    uid, token = re.search(r"uid=(\S+)&token=(\S+)", mail.outbox[0].body).groups()
    assert c.post(A + "verificar-email/", {"uid": uid, "token": token}).status_code == 204
    r = c.post(A + "login/", {"email": "ana@example.com", "password": "una-clave-muy-larga-77"})
    assert r.status_code == 200 and "access" in r.json() and r.cookies["refresh"]["httponly"]
    c2 = APIClient()
    c2.credentials(HTTP_AUTHORIZATION="Bearer " + r.json()["access"])
    assert c2.get(A + "me/").json()["email"] == "ana@example.com"
    assert c.post(A + "refresh/").status_code == 200
    assert c.post(A + "logout/").status_code == 204
    assert c.post(A + "refresh/").status_code == 401


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
