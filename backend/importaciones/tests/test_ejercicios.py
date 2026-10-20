import io
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from openpyxl import Workbook

from conftest import CategoriaFactory, HogarFactory
from finanzas.models import Movimiento
from importaciones import services
from importaciones.models import FilaImportacion, Importacion, PerfilBanco
from importaciones.tasks import caducar_vistas_previas

from .conftest import CSV_BANCO_A, url

pytestmark = pytest.mark.django_db
E, A = Importacion.Estado, FilaImportacion.Accion

# Un banco "raro": cabeceras que no se parecen a nada conocido y fechas a la americana
CSV_RARO = (
    b"Op;Txt;Ref;Cant\n"
    b"10/01/2026;PANADERIA SOL;8812;-2,40\n"
    b"10/02/2026;GASOLINERA NORTE;8813;-50,00\n"
    b"10/15/2026;TRANSFERENCIA RECIBIDA;8814;300,00\n"
)


@pytest.fixture
def subir_con_perfil(cliente, django_capture_on_commit_callbacks):
    def _subir(usuario, hogar, cuenta, contenido, perfil, nombre="extracto.csv"):
        datos = {"archivo": SimpleUploadedFile(nombre, contenido), "cuenta": cuenta.pk, "perfil": perfil}
        with django_capture_on_commit_callbacks(execute=True):
            return cliente(usuario).post(url(hogar), datos, format="multipart")

    return _subir


def perfiles(hogar):
    return f"/api/v1/hogares/{hogar.pk}/perfiles-banco/"


# ── 1. Perfiles de banco ──
def test_sin_perfil_falla_y_con_perfil_se_lee(escenario, subir, cliente, subir_con_perfil):
    hogar, roles, cuenta = escenario
    r = subir(hogar, roles["miembro"], cuenta, CSV_RARO)
    fallida = Importacion.objects.get(pk=r.data["id"])
    assert fallida.estado == E.ERROR and "perfil de banco" in fallida.error

    r = cliente(roles["miembro"]).post(
        perfiles(hogar),
        {
            "nombre": "Banco raro",
            "separador": ";",
            "columnas": {"fecha": 0, "concepto": 1, "importe": 3},
            "formato_fecha": "%m/%d/%Y",
        },
        format="json",
    )
    assert r.status_code == 201, r.data
    # el mismo archivo se puede volver a subir: la importación anterior acabó en error
    r = subir_con_perfil(roles["miembro"], hogar, cuenta, CSV_RARO, r.data["id"])
    imp = Importacion.objects.get(pk=r.data["id"])
    assert imp.estado == E.VISTA_PREVIA and imp.perfil.nombre == "Banco raro"
    filas = list(imp.filas.values_list("numero", "fecha", "concepto", "importe"))
    assert filas[0] == (2, date(2026, 10, 1), "PANADERIA SOL", Decimal("-2.40"))
    assert filas[2][1] == date(2026, 10, 15)  # mes/día: 15 no puede ser un mes


@pytest.mark.parametrize(
    "cambios, error",
    [
        ({"columnas": {"fecha": 0, "concepto": 1}}, "importe"),
        ({"columnas": {"fecha": 0, "concepto": 1, "importe": "3"}}, "entero"),
        ({"columnas": {"fecha": 0, "concepto": 0, "importe": 3}}, "misma columna"),
        ({"columnas": {"fecha": 0, "concepto": 1, "importe": 3, "iban": 4}}, "desconocidos"),
        ({"formato_fecha": "%d"}, "Falta el año"),
        ({"formato_fecha": "%d/%d/%Y"}, "Formato no válido"),
        ({"formato_fecha": "hola"}, "Falta el año"),
    ],
)
def test_validacion_del_perfil(escenario, cliente, cambios, error):
    hogar, roles, _ = escenario
    datos = {"nombre": "X", "columnas": {"fecha": 0, "concepto": 1, "importe": 3}} | cambios
    r = cliente(roles["miembro"]).post(perfiles(hogar), datos, format="json")
    assert r.status_code == 400 and error in str(r.data)


def test_no_se_usa_el_perfil_de_otro_hogar(escenario, subir_con_perfil):
    hogar, roles, cuenta = escenario
    ajeno = PerfilBanco.objects.create(hogar=HogarFactory(), nombre="Ajeno", columnas={"fecha": 0})
    r = subir_con_perfil(roles["miembro"], hogar, cuenta, CSV_RARO, ajeno.pk)
    assert r.status_code == 400 and "perfil" in r.data["errors"]


# ── 2. Excel ──
def xlsx(filas) -> bytes:
    libro = Workbook()
    hoja = libro.active
    for fila in filas:
        hoja.append(fila)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


EXCEL = xlsx(
    [
        ["Movimientos de la cuenta ES12 3456"],  # título antes de la tabla
        [],
        ["Fecha operación", "Concepto", "Importe (EUR)", "Importe", "Saldo"],
        [datetime(2026, 10, 1), "COMPRA MERCADONA", None, -45.3, 1954.7],  # fecha y números de verdad
        [datetime(2026, 10, 2), "NÓMINA ACME", None, 2100, 4054.7],
        ["03/10/2026", "RECIBO LUZ", None, "-61,22", "3.993,48"],  # algunos bancos guardan texto
    ]
)


def test_excel_reutiliza_la_deteccion_de_columnas(escenario, subir):
    hogar, roles, cuenta = escenario
    r = subir(hogar, roles["miembro"], cuenta, EXCEL, "extracto.xlsx")
    imp = Importacion.objects.get(pk=r.data["id"])
    assert imp.formato == "xlsx" and imp.estado == E.VISTA_PREVIA, imp.error
    assert list(imp.filas.values_list("numero", "fecha", "importe")) == [
        (4, date(2026, 10, 1), Decimal("-45.30")),
        (5, date(2026, 10, 2), Decimal("2100")),
        (6, date(2026, 10, 3), Decimal("-61.22")),
    ]
    assert imp.avisos == []  # los saldos cuadran: ni floats con decimales raros ni filas perdidas


def test_excel_con_perfil(escenario, subir_con_perfil):
    hogar, roles, cuenta = escenario
    contenido = xlsx([["Dia", "Texto", "Cantidad"], ["2026-10-05", "BIZUM", 25.5]])
    perfil = PerfilBanco.objects.create(
        hogar=hogar, nombre="Excel", columnas={"fecha": 0, "concepto": 1, "importe": 2}, formato_fecha="%Y-%m-%d"
    )
    r = subir_con_perfil(roles["miembro"], hogar, cuenta, contenido, perfil.pk, "e.xlsx")
    fila = Importacion.objects.get(pk=r.data["id"]).filas.get()
    assert (fila.fecha, fila.importe) == (date(2026, 10, 5), Decimal("25.50"))


# ── 3. Vista previa editable ──
def test_cambiar_categoria_de_una_fila_antes_de_confirmar(escenario, subir, cliente, en_commit):
    hogar, roles, cuenta = escenario
    ocio = CategoriaFactory(hogar=hogar, nombre="Ocio")
    imp = Importacion.objects.get(pk=subir(hogar, roles["miembro"], cuenta).data["id"])
    cafe = imp.filas.filter(concepto="CAFETERÍA LA PLAZA").first()
    base = f"{url(hogar)}{imp.pk}/filas/"

    assert cliente(roles["lector"]).patch(f"{base}{cafe.pk}/", {"categoria": ocio.pk}).status_code == 403
    ajena = CategoriaFactory(hogar=HogarFactory())
    assert cliente(roles["miembro"]).patch(f"{base}{cafe.pk}/", {"categoria": ajena.pk}).status_code == 400
    r = cliente(roles["miembro"]).patch(f"{base}{cafe.pk}/", {"categoria": ocio.pk})
    assert r.status_code == 200 and r.data["categoria"] == ocio.pk

    en_commit(cliente(roles["miembro"]).post, url(hogar, f"{imp.pk}/confirmar/"), {})
    cafe.refresh_from_db()
    assert cafe.movimiento.categoria == ocio  # importar_lote respeta lo elegido
    # ya importada: cambiarla no tendría efecto → 409
    assert cliente(roles["miembro"]).patch(f"{base}{cafe.pk}/", {"categoria": None}).status_code == 409


def test_filas_de_otra_importacion_o_duplicadas_no_se_editan(escenario, subir, cliente, en_commit):
    hogar, roles, cuenta = escenario
    primera = Importacion.objects.get(pk=subir(hogar, roles["miembro"], cuenta).data["id"])
    en_commit(cliente(roles["miembro"]).post, url(hogar, f"{primera.pk}/confirmar/"), {})
    # el mismo contenido con una fila más: las 5 anteriores salen duplicadas
    otra = CSV_BANCO_A + "06/10/2026;06/10/2026;FARMACIA;-9,99;3.980,49\n".encode("cp1252")
    segunda = Importacion.objects.get(pk=subir(hogar, roles["miembro"], cuenta, otra).data["id"])
    duplicada = segunda.filas.filter(accion=A.DUPLICADA).first()
    c = cliente(roles["miembro"])
    assert c.patch(f"{url(hogar)}{segunda.pk}/filas/{duplicada.pk}/", {"categoria": None}).status_code == 404
    de_la_primera = primera.filas.first()
    assert c.patch(f"{url(hogar)}{segunda.pk}/filas/{de_la_primera.pk}/", {"categoria": None}).status_code == 404


# ── 4. Caducidad ──
def test_caducar_borra_vistas_previas_abandonadas_con_su_archivo(escenario, subir, django_capture_on_commit_callbacks):
    hogar, roles, cuenta = escenario
    vieja = Importacion.objects.get(pk=subir(hogar, roles["miembro"], cuenta).data["id"])
    reciente = Importacion.objects.get(
        pk=subir(hogar, roles["miembro"], cuenta, CSV_BANCO_A + b"\n", "otro.csv").data["id"]
    )
    completada_vieja = Importacion.objects.create(
        hogar=hogar,
        cuenta=cuenta,
        archivo="importaciones/x.csv",
        formato="csv",
        huella_archivo="z",
        estado=E.COMPLETADA,
    )
    hace = timezone.now() - timedelta(days=8)
    Importacion.objects.filter(pk__in=[vieja.pk, completada_vieja.pk]).update(actualizado=hace)
    Importacion.objects.filter(pk=reciente.pk).update(actualizado=timezone.now() - timedelta(days=6))
    archivo = vieja.archivo.name
    assert default_storage.exists(archivo)

    with django_capture_on_commit_callbacks(execute=True):  # el archivo se borra al confirmar la transacción
        assert caducar_vistas_previas() == 1

    assert not Importacion.objects.filter(pk=vieja.pk).exists()
    assert not FilaImportacion.objects.filter(importacion_id=vieja.pk).exists()
    assert not default_storage.exists(archivo)
    assert Importacion.objects.filter(pk__in=[reciente.pk, completada_vieja.pk]).count() == 2
    assert not Movimiento.objects.exists()


def test_caducar_esta_en_beat(settings):
    tareas = {t["task"] for t in settings.CELERY_BEAT_SCHEDULE.values()}
    assert "importaciones.tasks.caducar_vistas_previas" in tareas
    assert services.caducar(dias=7) == 0  # sin nada que borrar, no falla
