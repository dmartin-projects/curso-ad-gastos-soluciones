import factory
import pytest
from django.core.cache import cache
from factory.django import DjangoModelFactory
from rest_framework.test import APIClient

from hogares.models import Hogar, Membresia
from usuarios.models import Usuario


class UsuarioFactory(DjangoModelFactory):
    class Meta:
        model = Usuario
        django_get_or_create = ("email",)

    email = factory.Sequence(lambda n: f"usuario{n}@example.com")
    nombre = factory.Faker("first_name", locale="es_ES")
    password = factory.django.Password("clave-segura-123")


class HogarFactory(DjangoModelFactory):
    class Meta:
        model = Hogar

    nombre = factory.Sequence(lambda n: f"Hogar {n}")


class MembresiaFactory(DjangoModelFactory):
    class Meta:
        model = Membresia

    hogar = factory.SubFactory(HogarFactory)
    usuario = factory.SubFactory(UsuarioFactory)
    rol = Membresia.Rol.ADMIN


@pytest.fixture(autouse=True)
def cache_limpia():
    """La caché locmem vive mientras dura el proceso: sin esto, un test hereda la del anterior (módulo 31)."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def api():
    return APIClient()


@pytest.fixture
def cliente():
    """cliente(usuario) → APIClient autenticado como ese usuario."""

    def _cliente(usuario):
        c = APIClient()
        c.force_authenticate(usuario)
        return c

    return _cliente


@pytest.fixture
def hogar_con_roles(db):
    """Un hogar con un admin, un miembro, un lector y un usuario ajeno."""
    hogar = HogarFactory()
    roles = {rol: MembresiaFactory(hogar=hogar, rol=rol).usuario for rol in Membresia.Rol.values}
    roles["ajeno"] = UsuarioFactory()
    return hogar, roles


class CuentaFactory(DjangoModelFactory):
    class Meta:
        model = "finanzas.Cuenta"

    hogar = factory.SubFactory(HogarFactory)
    nombre = factory.Sequence(lambda n: f"Cuenta {n}")


class CategoriaFactory(DjangoModelFactory):
    class Meta:
        model = "finanzas.Categoria"

    hogar = factory.SubFactory(HogarFactory)
    nombre = factory.Sequence(lambda n: f"Categoría {n}")


class MovimientoFactory(DjangoModelFactory):
    class Meta:
        model = "finanzas.Movimiento"

    cuenta = factory.SubFactory(CuentaFactory)
    hogar = factory.SelfAttribute("cuenta.hogar")
    fecha = factory.Faker("date_this_year")
    importe = factory.Faker("pydecimal", left_digits=3, right_digits=2, max_value=-1, min_value=-500)
    concepto = factory.Faker("company", locale="es_ES")
