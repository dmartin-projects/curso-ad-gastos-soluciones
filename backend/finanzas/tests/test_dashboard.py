from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from conftest import CategoriaFactory, CuentaFactory, MovimientoFactory
from finanzas import dashboard
from finanzas.models import Comercio, Presupuesto

pytestmark = pytest.mark.django_db
OCT = date(2026, 10, 1)


@pytest.fixture
def datos(hogar_con_roles):
    hogar, roles = hogar_con_roles
    cuenta = CuentaFactory(hogar=hogar)
    comida = CategoriaFactory(hogar=hogar, nombre="Comida", color="#4caf50")
    fruta = CategoriaFactory(hogar=hogar, nombre="Fruta", padre=comida)
    ocio = CategoriaFactory(hogar=hogar, nombre="Ocio")
    mercadona = Comercio.objects.create(nombre="Mercadona")

    def mov(dia, importe, categoria=None, mes=10, **extra):
        return MovimientoFactory(
            cuenta=cuenta, fecha=date(2026, mes, dia), importe=Decimal(importe), categoria=categoria, **extra
        )

    mov(1, "-10", comida, comercio=mercadona)
    mov(1, "-5", fruta, comercio=mercadona)
    mov(3, "-20", ocio)
    mov(3, "1000.00")
    mov(7, "-2.50", comida, revisado=False)
    mov(5, "-30", ocio, mes=9)
    Presupuesto.objects.create(hogar=hogar, categoria=comida, mes=OCT, importe=Decimal("10"))
    return hogar, roles, comida, ocio


def url(hogar):
    return f"/api/v1/hogares/{hogar.pk}/dashboard/"


def test_calculo_del_mes(datos):
    hogar, _, comida, ocio = datos

    d = dashboard.calcular(hogar, OCT)

    assert (d["gastos"], d["ingresos"], d["balance"]) == (Decimal("37.50"), Decimal("1000.00"), Decimal("962.50"))
    assert d["gastos_mes_anterior"] == Decimal("30.00") and d["variacion"] == Decimal("25.0")
    # la subcategoría Fruta suma en Comida
    assert [(c["nombre"], c["total"]) for c in d["por_categoria"]] == [
        ("Ocio", Decimal("20")),
        ("Comida", Decimal("17.50")),
    ]
    assert [(f["fecha"].day, f["gasto"], f["acumulado"]) for f in d["acumulado"]] == [
        (1, Decimal("15.00"), Decimal("15.00")),
        (3, Decimal("20.00"), Decimal("35.00")),
        (7, Decimal("2.50"), Decimal("37.50")),
    ]
    assert len(d["evolucion"]) == 12 and d["evolucion"][0]["mes"] == date(2025, 11, 1)
    assert d["evolucion"][0]["gastos"] == 0 and d["evolucion"][-2]["gastos"] == Decimal("30.00")
    assert (
        d["top_comercios"][0] | {"nombre": "Mercadona", "total": Decimal("15.00"), "veces": 2} == d["top_comercios"][0]
    )
    assert d["presupuestos"] == [
        {"categoria": "Comida", "importe": Decimal("10.00"), "gastado": Decimal("17.50"), "porcentaje": 175}
    ]
    assert d["pendientes_revision"] == 1


def test_api_permisos_formato_y_validacion(datos, cliente):
    hogar, roles, _, _ = datos
    r = cliente(roles["lector"]).get(url(hogar), {"mes": "2026-10"})
    assert r.status_code == 200
    assert r.data["mes"] == "2026-10" and r.data["gastos"] == "37.50" and r.data["evolucion"][-1]["mes"] == "2026-10"
    assert cliente(roles["ajeno"]).get(url(hogar)).status_code == 404
    assert cliente(roles["lector"]).get(url(hogar), {"mes": "octubre"}).status_code == 400


@pytest.mark.parametrize("zona, esperado", [("Europe/Madrid", "2026-11"), ("America/New_York", "2026-10")])
def test_el_mes_por_defecto_depende_de_la_zona_del_hogar(datos, cliente, time_machine, zona, esperado):
    hogar, roles, _, _ = datos
    hogar.zona_horaria = zona
    hogar.save()
    time_machine.move_to(datetime(2026, 10, 31, 23, 30, tzinfo=ZoneInfo("UTC")))  # en Madrid ya es 1 de noviembre
    assert cliente(roles["lector"]).get(url(hogar)).data["mes"] == esperado


def test_cache_etag_e_invalidacion(datos, cliente, django_assert_num_queries, django_capture_on_commit_callbacks):
    hogar, roles, _, ocio = datos
    c = cliente(roles["miembro"])

    primera = c.get(url(hogar), {"mes": "2026-10"})
    with django_assert_num_queries(1):  # solo la membresía: el resto sale de la caché
        assert c.get(url(hogar), {"mes": "2026-10"}).data == primera.data
    etag = primera.headers["ETag"]
    assert c.get(url(hogar), {"mes": "2026-10"}, HTTP_IF_NONE_MATCH=etag).status_code == 304

    with django_capture_on_commit_callbacks(execute=True):  # un gasto nuevo → movimientos_cambiados → versión nueva
        c.post(
            f"/api/v1/hogares/{hogar.pk}/movimientos/",
            {"fecha": "2026-10-09", "importe": "-12.50", "concepto": "Cine", "cuenta": ocio.hogar.cuentas.first().pk},
        )

    r = c.get(url(hogar), {"mes": "2026-10"}, HTTP_IF_NONE_MATCH=etag)
    assert r.status_code == 200 and r.headers["ETag"] != etag
    assert r.data["gastos"] == "50.00"


def test_renombrar_una_categoria_invalida(datos, cliente, django_capture_on_commit_callbacks):
    hogar, roles, comida, _ = datos
    c = cliente(roles["admin"])
    c.get(url(hogar), {"mes": "2026-10"})
    with django_capture_on_commit_callbacks(execute=True):
        c.patch(f"/api/v1/hogares/{hogar.pk}/categorias/{comida.pk}/", {"nombre": "Alimentación"})
    nombres = [x["nombre"] for x in c.get(url(hogar), {"mes": "2026-10"}).data["por_categoria"]]
    assert "Alimentación" in nombres


def test_borrar_un_presupuesto_invalida(datos, cliente, django_capture_on_commit_callbacks):
    hogar, roles, comida, _ = datos
    c = cliente(roles["admin"])
    assert len(c.get(url(hogar), {"mes": "2026-10"}).data["presupuestos"]) == 1
    presupuesto = Presupuesto.objects.get(hogar=hogar, categoria=comida)
    with django_capture_on_commit_callbacks(execute=True):
        assert c.delete(f"/api/v1/hogares/{hogar.pk}/presupuestos/{presupuesto.pk}/").status_code == 204
    assert c.get(url(hogar), {"mes": "2026-10"}).data["presupuestos"] == []
