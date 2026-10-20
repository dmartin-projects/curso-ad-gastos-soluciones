import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor

from conftest import CategoriaFactory, CuentaFactory, HogarFactory, MovimientoFactory
from finanzas.models import Movimiento


@pytest.fixture
def dos_hogares(db):
    a, b = HogarFactory(), HogarFactory()
    return a, b, CuentaFactory(hogar=a), CategoriaFactory(hogar=b)


def test_clean_rechaza_categoria_de_otro_hogar(dos_hogares):
    a, b, cuenta_a, categoria_b = dos_hogares
    m = MovimientoFactory.build(hogar=a, cuenta=cuenta_a, categoria=categoria_b)
    with pytest.raises(ValidationError) as e:
        m.full_clean()
    assert "categoria" in e.value.message_dict


def test_la_bd_rechaza_categoria_de_otro_hogar(dos_hogares):
    a, b, cuenta_a, categoria_b = dos_hogares
    m = MovimientoFactory(hogar=a, cuenta=cuenta_a)
    # update() se salta clean() y el serializer: solo la BD puede pararlo.
    # La FK es DEFERRABLE INITIALLY DEFERRED: el error salta al confirmar, por eso SET CONSTRAINTS ALL IMMEDIATE.
    with pytest.raises(IntegrityError, match="movimiento_categoria_mismo_hogar"), transaction.atomic():
        with connection.cursor() as c:
            c.execute("SET CONSTRAINTS ALL IMMEDIATE")
        Movimiento.objects.filter(pk=m.pk).update(categoria=categoria_b)


def test_borrar_la_categoria_solo_anula_categoria(db):
    hogar = HogarFactory()
    categoria = CategoriaFactory(hogar=hogar)
    m = MovimientoFactory(hogar=hogar, cuenta=CuentaFactory(hogar=hogar), categoria=categoria)
    categoria.delete()
    m.refresh_from_db()
    assert m.categoria_id is None and m.hogar_id == hogar.pk


def test_api_tampoco_acepta_categoria_ajena(cliente, hogar_con_roles):
    hogar, roles = hogar_con_roles
    cuenta = CuentaFactory(hogar=hogar)
    ajena = CategoriaFactory(hogar=HogarFactory())
    r = cliente(roles["miembro"]).post(
        f"/api/v1/hogares/{hogar.pk}/movimientos/",
        {"cuenta": cuenta.pk, "categoria": ajena.pk, "fecha": "2026-01-10", "importe": "-5", "concepto": "x"},
    )
    assert r.status_code == 400 and "categoria" in str(r.json())


@pytest.mark.django_db(transaction=True)
def test_migracion_asigna_comercios():
    antes = [("finanzas", "0003_categoria_mismo_hogar")]
    executor = MigrationExecutor(connection)
    executor.migrate(antes)  # la BD, como estaba ANTES de la migración de datos
    # ⚠️ Modelos HISTÓRICOS, no los de models.py ni las factories: las tablas aún no tienen las columnas
    # de migraciones posteriores, y los modelos actuales (y sus señales) las consultarían.
    apps = executor.loader.project_state(antes).apps
    Hogar, Cuenta = apps.get_model("hogares", "Hogar"), apps.get_model("finanzas", "Cuenta")
    Comercio, Movimiento = apps.get_model("finanzas", "Comercio"), apps.get_model("finanzas", "Movimiento")
    hogar = Hogar.objects.create(nombre="Casa")
    cuenta = Cuenta.objects.create(hogar=hogar, nombre="Común")
    # el modelo histórico no tiene el save() que normaliza: se rellena a mano
    mercadona = Comercio.objects.create(nombre="Mercadona", nombre_normalizado="mercadona")
    lidl = Comercio.objects.create(nombre="Lidl", nombre_normalizado="lidl")

    def mov(concepto, comercio=None):
        return Movimiento.objects.create(
            hogar=hogar, cuenta=cuenta, fecha="2026-10-01", importe=-1, concepto=concepto, comercio=comercio
        ).pk

    coincide, parecido, ya_tenia = mov("MERCADONA, S.A. 1234"), mov("MERCADONA MADRID"), mov("Mercadona", lidl)

    executor = MigrationExecutor(connection)  # el grafo cambió: hay que recargarlo
    executor.migrate(executor.loader.graph.leaf_nodes())

    comercio = dict(Movimiento.objects.values_list("pk", "comercio_id"))  # vale el histórico: solo leemos ids
    assert comercio[coincide] == mercadona.pk  # coincidencia exacta tras normalizar
    assert comercio[parecido] is None  # "mercadona madrid" ≠ "mercadona": nada de aproximaciones
    assert comercio[ya_tenia] == lidl.pk  # no pisa lo que ya estaba
