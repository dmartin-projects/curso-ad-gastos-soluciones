import logging
from datetime import date
from decimal import Decimal

import pytest
from django.core.cache import cache

from conftest import CategoriaFactory, CuentaFactory, HogarFactory, MovimientoFactory
from finanzas import dashboard

pytestmark = pytest.mark.django_db
OCTUBRE = date(2026, 10, 1)


@pytest.fixture
def casa(db):
    hogar = HogarFactory()
    return hogar, CuentaFactory(hogar=hogar)


def gasto(cuenta, fecha, importe, categoria=None):
    return MovimientoFactory(cuenta=cuenta, fecha=fecha, importe=Decimal(importe), categoria=categoria)


# ── 1. Comparativa diaria ──
def test_comparativa_dia_a_dia_con_el_mes_anterior(casa, time_machine):
    time_machine.move_to(date(2026, 10, 15))
    hogar, cuenta = casa
    gasto(cuenta, date(2026, 9, 1), "-10")
    gasto(cuenta, date(2026, 9, 10), "-5")
    gasto(cuenta, date(2026, 10, 2), "-3")
    gasto(cuenta, date(2026, 10, 2), "-4")
    gasto(cuenta, date(2026, 10, 5), "-1")

    filas = {f["dia"]: f for f in dashboard.calcular(hogar, OCTUBRE)["comparativa"]}
    assert len(filas) == 31  # octubre manda (septiembre tiene 30)
    assert (filas[1]["este_mes"], filas[1]["mes_anterior"]) == (0, 10)
    assert (filas[2]["este_mes"], filas[9]["mes_anterior"]) == (7, 10)  # sin gasto ese día: se mantiene
    assert (filas[15]["este_mes"], filas[15]["mes_anterior"]) == (8, 15)
    assert filas[16]["este_mes"] is None  # el futuro no se pinta
    assert filas[31]["mes_anterior"] is None  # septiembre no tiene día 31


def test_comparativa_de_un_mes_pasado_llega_hasta_el_final(casa, time_machine):
    time_machine.move_to(date(2026, 10, 15))
    hogar, cuenta = casa
    gasto(cuenta, date(2026, 9, 20), "-10")
    filas = dashboard.calcular(hogar, date(2026, 9, 1))["comparativa"]
    assert len(filas) == 31 and filas[29]["este_mes"] == 10  # día 30: septiembre completo


# ── 2. Ranking con Rank() ──
def test_ranking_frente_a_los_12_meses_anteriores(casa):
    hogar, cuenta = casa
    super_ = CategoriaFactory(hogar=hogar, nombre="Súper")
    fruta = CategoriaFactory(hogar=hogar, nombre="Fruta", padre=super_)
    ocio = CategoriaFactory(hogar=hogar, nombre="Ocio")
    mes = OCTUBRE
    for i in range(13):  # octubre 2026 (100) y los 12 anteriores, crecientes hacia atrás: 110, 120… 220
        gasto(cuenta, mes.replace(day=10), f"-{100 + i * 10}", super_)
        mes = dashboard.mes_anterior(mes)
    gasto(cuenta, date(2026, 10, 11), "-115", fruta)  # octubre: 100 + 115 = 215 → solo lo supera el 220
    gasto(cuenta, date(2025, 9, 1), "-999", super_)  # hace 13 meses: fuera de la ventana
    gasto(cuenta, date(2026, 10, 3), "-5", ocio)  # primera vez que se gasta en ocio

    r = {f["nombre"]: f for f in dashboard.ranking(hogar, OCTUBRE)}
    assert (r["Súper"]["posicion"], r["Súper"]["de"]) == (2, 13)  # la hija suma en el padre
    assert (r["Ocio"]["posicion"], r["Ocio"]["de"]) == (1, 1)
    assert list(r) == ["Ocio", "Súper"]  # ordenado por puesto


def test_ranking_en_la_api(casa, cliente):
    from conftest import MembresiaFactory

    hogar, cuenta = casa
    m = MembresiaFactory(hogar=hogar, rol="lector")
    gasto(cuenta, date(2026, 10, 3), "-5", CategoriaFactory(hogar=hogar, nombre="Ocio"))
    r = cliente(m.usuario).get(f"/api/v1/hogares/{hogar.pk}/dashboard/", {"mes": "2026-10"})
    assert r.data["ranking"][0]["posicion"] == 1 and len(r.data["comparativa"]) == 31


# ── 3. Calentar la caché ──
def test_tras_un_cambio_el_mes_actual_ya_esta_en_cache(casa, cliente, django_capture_on_commit_callbacks):
    from conftest import MembresiaFactory

    hogar, cuenta = casa
    m = MembresiaFactory(hogar=hogar, rol="miembro")
    hoy = dashboard.hoy(hogar)
    with django_capture_on_commit_callbacks(execute=True):
        cliente(m.usuario).post(
            f"/api/v1/hogares/{hogar.pk}/movimientos/",
            {"fecha": hoy, "importe": "-9.99", "concepto": "Pan", "cuenta": cuenta.pk},
        )
    v = dashboard.version(hogar.pk)
    calentado = cache.get(dashboard.clave(hogar.pk, v, hoy.replace(day=1)))
    assert calentado is not None and calentado["gastos"] == Decimal("9.99")


def test_calentar_se_agrupa(casa, monkeypatch, django_capture_on_commit_callbacks):
    from finanzas import tasks

    hogar, cuenta = casa
    llamadas = []
    monkeypatch.setattr(tasks.calentar_dashboard, "apply_async", lambda args, **kw: llamadas.append(args))
    with django_capture_on_commit_callbacks(execute=True):
        for _ in range(20):
            gasto(cuenta, dashboard.hoy(hogar), "-1")
    assert llamadas == [(hogar.pk,)]  # 20 cambios, un recálculo


# ── 4. Medir ──
def test_el_calculo_queda_en_los_logs(casa, caplog):
    hogar, _ = casa
    with caplog.at_level(logging.INFO, logger="finanzas.dashboard"):
        dashboard.obtener(hogar, OCTUBRE)
        dashboard.obtener(hogar, OCTUBRE)  # de la caché: no se recalcula ni se registra
    registros = [r for r in caplog.records if "calculado en" in r.getMessage()]
    assert len(registros) == 1 and registros[0].duracion_ms > 0 and registros[0].mes == "2026-10"
