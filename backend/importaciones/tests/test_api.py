from datetime import date
from decimal import Decimal

import pytest

from conftest import CategoriaFactory, MovimientoFactory
from core.models import RegistroAuditoria
from finanzas.models import Comercio, Movimiento
from finanzas.signals import movimientos_cambiados
from importaciones import services
from importaciones.models import FilaImportacion, Importacion

from .conftest import CSV_BANCO_A, archivo

pytestmark = pytest.mark.django_db
E, A = Importacion.Estado, FilaImportacion.Accion


def url(hogar, sufijo=""):
    return f"/api/v1/hogares/{hogar.pk}/importaciones/{sufijo}"


def test_flujo_completo_vista_previa_conciliacion_e_importacion(escenario, subir, cliente, en_commit, settings):
    hogar, roles, cuenta = escenario
    settings.IMPORTACION_TAMANO_LOTE = 2  # 5 filas → 3 lotes en el chord
    luz = CategoriaFactory(hogar=hogar, nombre="Luz")
    iberdrola = Comercio.objects.create(nombre="Iberdrola")
    MovimientoFactory(cuenta=cuenta, comercio=iberdrola, categoria=luz, fecha=date(2026, 9, 3))  # historial
    # el usuario ya apuntó a mano el gasto del súper (el día 2; el banco lo carga el día 1)
    a_mano = MovimientoFactory(cuenta=cuenta, fecha=date(2026, 10, 2), importe=Decimal("-45.30"), concepto="Súper")

    r = subir(hogar, roles["miembro"], cuenta)

    assert r.status_code == 202 and r.data["estado"] == E.PENDIENTE
    imp = Importacion.objects.get(pk=r.data["id"])
    assert imp.estado == E.VISTA_PREVIA and imp.formato == "csv"
    assert imp.resumen | {"gastos": "-109.52", "ingresos": "2100.00", "conciliar": 1, "a_importar": 5} == imp.resumen
    assert Movimiento.objects.filter(origen="extracto").count() == 0  # la vista previa no crea nada

    filas = cliente(roles["lector"]).get(url(hogar, f"{imp.pk}/filas/"), {"accion": "conciliar"}).data["results"]
    assert len(filas) == 1 and filas[0]["coincide_con"] == a_mano.pk

    cambios = []
    movimientos_cambiados.connect(lambda **kw: cambios.append(kw), weak=False, dispatch_uid="test")
    try:
        r = en_commit(cliente(roles["miembro"]).post, url(hogar, f"{imp.pk}/confirmar/"), {})
    finally:
        movimientos_cambiados.disconnect(dispatch_uid="test")

    assert r.status_code == 202
    imp.refresh_from_db()
    assert (imp.estado, imp.procesadas, imp.creados, imp.conciliados) == (E.COMPLETADA, 5, 4, 1)
    a_mano.refresh_from_db()
    assert a_mano.huella  # el gasto manual queda vinculado a la fila del banco: no se duplica
    recibo = Movimiento.objects.get(concepto="RECIBO IBERDROLA CLIENTES")
    assert recibo.comercio == iberdrola and recibo.categoria == luz  # categoría aprendida del hogar
    assert Movimiento.objects.filter(concepto="CAFETERÍA LA PLAZA").count() == 2  # dos cafés legítimos
    assert cambios[0]["hogar_id"] == hogar.pk and cambios[0]["meses"] == {date(2026, 10, 1)}


def test_reimportar_un_extracto_solapado_solo_crea_lo_nuevo(escenario, subir, cliente, en_commit):
    hogar, roles, cuenta = escenario
    primero = subir(hogar, roles["miembro"], cuenta).data["id"]
    en_commit(cliente(roles["miembro"]).post, url(hogar, f"{primero}/confirmar/"), {})
    # el extracto del mes siguiente repite los dos últimos días y trae uno nuevo
    solapado = (
        "Fecha;Concepto;Importe\n"
        "05/10/2026;CAFETERIA LA PLAZA;-1,50\n05/10/2026;Cafetería la Plaza;-1,50\n06/10/2026;FARMACIA;-8,95\n"
    ).encode()

    imp = Importacion.objects.get(pk=subir(hogar, roles["miembro"], cuenta, solapado).data["id"])

    assert imp.duplicados == 2 and imp.resumen["a_importar"] == 1
    en_commit(cliente(roles["miembro"]).post, url(hogar, f"{imp.pk}/confirmar/"), {})
    assert Movimiento.objects.filter(concepto__icontains="cafeter").count() == 2
    assert Movimiento.objects.filter(concepto="FARMACIA").exists()


def test_separar_una_fila_que_no_era_el_mismo_gasto(escenario, subir, cliente, en_commit):
    hogar, roles, cuenta = escenario
    MovimientoFactory(cuenta=cuenta, fecha=date(2026, 10, 1), importe=Decimal("-45.30"))
    imp = Importacion.objects.get(pk=subir(hogar, roles["miembro"], cuenta).data["id"])
    fila = imp.filas.get(accion=A.CONCILIAR)

    en_commit(cliente(roles["miembro"]).post, url(hogar, f"{imp.pk}/confirmar/"), {"separar": [fila.pk]})

    imp.refresh_from_db()
    assert (imp.creados, imp.conciliados) == (5, 0)
    assert Movimiento.objects.filter(importe=Decimal("-45.30")).count() == 2


def test_deshacer_solo_admin_y_deja_todo_como_estaba(escenario, subir, cliente, en_commit):
    hogar, roles, cuenta = escenario
    a_mano = MovimientoFactory(cuenta=cuenta, fecha=date(2026, 10, 1), importe=Decimal("-45.30"))
    imp_id = subir(hogar, roles["miembro"], cuenta).data["id"]
    en_commit(cliente(roles["miembro"]).post, url(hogar, f"{imp_id}/confirmar/"), {})

    assert cliente(roles["miembro"]).post(url(hogar, f"{imp_id}/deshacer/")).status_code == 403
    r = en_commit(cliente(roles["admin"]).post, url(hogar, f"{imp_id}/deshacer/"))

    assert r.status_code == 200 and r.data["estado"] == E.DESHECHA
    assert list(Movimiento.objects.all()) == [a_mano]
    assert RegistroAuditoria.objects.filter(accion="modificar", object_id=str(imp_id), usuario=roles["admin"]).exists()
    a_mano.refresh_from_db()
    assert a_mano.huella == ""
    # deshecha: el mismo archivo se puede volver a subir
    assert subir(hogar, roles["miembro"], cuenta).status_code == 202


def test_el_mismo_extracto_no_se_sube_dos_veces(escenario, subir):
    hogar, roles, cuenta = escenario
    subir(hogar, roles["miembro"], cuenta)
    r = subir(hogar, roles["miembro"], cuenta, nombre="copia.csv")
    assert r.status_code == 400 and "ya se importó" in r.data["errors"]["archivo"][0]


def test_dos_subidas_simultaneas_del_mismo_extracto(escenario, subir, monkeypatch):
    hogar, roles, cuenta = escenario
    original = services.subir

    def otra_subida_a_la_vez(**datos):
        Importacion.objects.create(
            hogar=datos["hogar"],
            cuenta=datos["cuenta"],
            archivo="importaciones/otro.csv",
            nombre_original="otro.csv",
            formato=datos["formato"],
            huella_archivo=datos["huella_archivo"],
        )
        return original(**datos)

    monkeypatch.setattr(services, "subir", otra_subida_a_la_vez)
    r = subir(hogar, roles["miembro"], cuenta)
    assert r.status_code == 400 and r.json()["errors"]["archivo"] == ["Este extracto ya se importó."]


def test_borrar_un_hogar_con_importaciones_y_tickets(escenario, subir, cliente):
    from tickets.models import Ticket

    hogar, roles, cuenta = escenario
    subir(hogar, roles["miembro"], cuenta)
    Ticket.objects.create(
        hogar=hogar, cuenta=cuenta, archivo="tickets/x.jpg", nombre_original="x.jpg", tipo="image/jpeg"
    )
    # Importacion.cuenta y Ticket.cuenta son RESTRICT: borrar el hogar entero sí puede (y no da un 500)
    assert cliente(roles["admin"]).delete(f"/api/v1/hogares/{hogar.pk}/").status_code == 204
    assert not Importacion.objects.filter(hogar=hogar).exists() and not Ticket.objects.filter(hogar=hogar).exists()


def test_archivo_binario_se_rechaza_y_csv_ilegible_acaba_en_error(escenario, subir):
    hogar, roles, cuenta = escenario
    assert subir(hogar, roles["miembro"], cuenta, b"\x89PNG\r\n\x1a\n\x00\x00", "extracto.png").status_code == 400
    # Un ZIP pasa el filtro de la subida (podría ser un .xlsx), pero el análisis no lo puede abrir (ejercicio 2)
    r = subir(hogar, roles["miembro"], cuenta, b"PK\x03\x04\x00\x00", "extracto.xlsx")
    assert Importacion.objects.get(pk=r.data["id"]).error.startswith("No se puede abrir el Excel")

    r = subir(hogar, roles["miembro"], cuenta, b"nombre;edad\nana;30\n")

    imp = Importacion.objects.get(pk=r.data["id"])
    assert imp.estado == E.ERROR and "columnas" in imp.error


def test_una_entrega_duplicada_de_un_lote_no_crea_nada(escenario, subir, cliente):
    hogar, roles, cuenta = escenario
    imp = Importacion.objects.get(pk=subir(hogar, roles["miembro"], cuenta).data["id"])
    ids = list(imp.filas.values_list("pk", flat=True))
    Importacion.objects.filter(pk=imp.pk).update(estado=E.IMPORTANDO)

    assert services.importar_lote(imp.pk, ids)["creados"] == 5
    assert services.importar_lote(imp.pk, ids)["creados"] == 0
    assert Movimiento.objects.count() == 5


def test_confirmar_dos_veces_es_409(escenario, subir, cliente, en_commit):
    hogar, roles, cuenta = escenario
    imp_id = subir(hogar, roles["miembro"], cuenta).data["id"]
    en_commit(cliente(roles["miembro"]).post, url(hogar, f"{imp_id}/confirmar/"), {})
    r = cliente(roles["miembro"]).post(url(hogar, f"{imp_id}/confirmar/"), {})
    assert r.status_code == 409


@pytest.mark.parametrize("rol, esperado", [("lector", 403), ("ajeno", 404)])
def test_permisos_de_subida(escenario, cliente, rol, esperado):
    hogar, roles, cuenta = escenario
    r = cliente(roles[rol]).post(url(hogar), {"archivo": archivo(CSV_BANCO_A), "cuenta": cuenta.pk}, format="multipart")
    assert r.status_code == esperado
