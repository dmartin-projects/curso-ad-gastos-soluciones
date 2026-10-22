from datetime import date
from decimal import Decimal

import pytest
from django.core import mail
from django.core.cache import cache

from conftest import CategoriaFactory, CuentaFactory, MovimientoFactory, UsuarioFactory
from finanzas.models import Movimiento, Presupuesto
from finanzas.servicios_presupuestos import comprobar_presupuestos
from finanzas.signals import movimientos_cambiados
from notificaciones.models import Notificacion

pytestmark = pytest.mark.django_db
T = Notificacion.Tipo
HOY = date(2026, 10, 15)


@pytest.fixture
def escenario(hogar_con_roles):
    hogar, roles = hogar_con_roles
    cuenta = CuentaFactory(hogar=hogar)
    super_ = CategoriaFactory(hogar=hogar, nombre="Súper")
    return hogar, roles, cuenta, super_


def gastar(cliente, roles, hogar, cuenta, categoria, importe, capturar):
    with capturar(execute=True):
        r = cliente(roles["miembro"]).post(
            f"/api/v1/hogares/{hogar.pk}/movimientos/",
            {"fecha": HOY, "importe": importe, "concepto": "Compra", "cuenta": cuenta.pk, "categoria": categoria.pk},
        )
    assert r.status_code == 201, r.data
    cache.clear()  # las comprobaciones se agrupan 10 s (core/agrupar.py); en el test, cada paso es otra "ventana"
    return r.data["id"]


def test_superar_un_presupuesto_avisa_una_vez_a_todo_el_hogar(
    escenario, cliente, django_capture_on_commit_callbacks, time_machine
):
    time_machine.move_to(HOY)
    hogar, roles, cuenta, super_ = escenario
    hija = CategoriaFactory(hogar=hogar, nombre="Fruta", padre=super_)
    Presupuesto.objects.create(hogar=hogar, categoria=super_, mes=date(2026, 10, 1), importe=Decimal("100"))

    gastar(cliente, roles, hogar, cuenta, super_, "-70.00", django_capture_on_commit_callbacks)
    assert not Notificacion.objects.exists()

    gastar(cliente, roles, hogar, cuenta, hija, "-40.00", django_capture_on_commit_callbacks)  # cuenta la subcategoría

    avisos = Notificacion.objects.filter(tipo=T.PRESUPUESTO_SUPERADO)
    assert {n.usuario for n in avisos} == {roles["admin"], roles["miembro"], roles["lector"]}
    assert avisos[0].titulo == "Presupuesto de Súper superado"
    assert avisos[0].mensaje == "Lleváis 110.00 € de 100.00 € en 10/2026."
    assert len(mail.outbox) == 3 and mail.outbox[0].subject == "Presupuesto de Súper superado"

    gastar(cliente, roles, hogar, cuenta, super_, "-5.00", django_capture_on_commit_callbacks)
    assert avisos.count() == 3  # ya avisado: no se repite


def test_al_volver_por_debajo_la_alerta_se_rearma(escenario):
    hogar, _, cuenta, super_ = escenario
    p = Presupuesto.objects.create(hogar=hogar, categoria=super_, mes=date(2026, 10, 1), importe=Decimal("100"))
    gasto = MovimientoFactory(cuenta=cuenta, categoria=super_, fecha=HOY, importe=Decimal("-150"))
    meses = [date(2026, 10, 1)]

    assert comprobar_presupuestos(hogar.pk, meses) == [p]
    assert comprobar_presupuestos(hogar.pk, meses) == []  # una segunda comprobación no vuelve a avisar
    gasto.delete()
    comprobar_presupuestos(hogar.pk, meses)
    p.refresh_from_db()
    assert p.alerta_enviada is False


def test_recategorizar_en_bloque_tambien_avisa(escenario, cliente, django_capture_on_commit_callbacks):
    hogar, roles, cuenta, super_ = escenario
    movs = MovimientoFactory.create_batch(3, cuenta=cuenta, fecha=date(2026, 9, 10))
    recibidos = []
    movimientos_cambiados.connect(lambda **kw: recibidos.append(kw), weak=False, dispatch_uid="t")
    try:
        with django_capture_on_commit_callbacks(execute=True):
            cliente(roles["miembro"]).post(
                f"/api/v1/hogares/{hogar.pk}/movimientos/recategorizar/",
                {"ids": [m.pk for m in movs], "categoria": super_.pk},
            )
    finally:
        movimientos_cambiados.disconnect(dispatch_uid="t")
    assert recibidos[-1]["meses"] == {date(2026, 9, 1)}


def test_cambiar_la_fecha_a_otro_mes_rearma_la_alerta_del_mes_de_antes(
    escenario, cliente, django_capture_on_commit_callbacks
):
    hogar, roles, cuenta, super_ = escenario
    p = Presupuesto.objects.create(hogar=hogar, categoria=super_, mes=date(2026, 10, 1), importe=Decimal("100"))
    gasto = MovimientoFactory(cuenta=cuenta, categoria=super_, fecha=HOY, importe=Decimal("-150"))
    comprobar_presupuestos(hogar.pk, [date(2026, 10, 1)])  # octubre: superado y avisado
    with django_capture_on_commit_callbacks(execute=True):
        r = cliente(roles["miembro"]).patch(
            f"/api/v1/hogares/{hogar.pk}/movimientos/{gasto.pk}/", {"fecha": "2026-09-28"}
        )
    assert r.status_code == 200
    p.refresh_from_db()
    assert p.alerta_enviada is False  # octubre ya no está superado: si se vuelve a superar, se avisará otra vez


def test_cualquier_save_avisa_tambien_del_mes_de_antes(escenario, django_capture_on_commit_callbacks):
    hogar, _, cuenta, super_ = escenario
    p = Presupuesto.objects.create(hogar=hogar, categoria=super_, mes=date(2026, 10, 1), importe=Decimal("100"))
    m = MovimientoFactory(cuenta=cuenta, categoria=super_, fecha=HOY, importe=Decimal("-150"))
    comprobar_presupuestos(hogar.pk, [date(2026, 10, 1)])
    m = Movimiento.objects.get(pk=m.pk)  # cargado desde la BD: from_db guarda la fecha
    m.fecha = date(2026, 9, 28)
    with django_capture_on_commit_callbacks(execute=True):
        m.save()  # sin pasar por la API (backoffice, un comando…): el receiver avisa de AMBOS meses
    p.refresh_from_db()
    assert p.alerta_enviada is False


@pytest.fixture
def senales():
    recibidas = []

    def receptor(sender, hogar_id, meses, **kwargs):
        recibidas.append(meses)

    movimientos_cambiados.connect(receptor, dispatch_uid="test-meses")
    yield recibidas
    movimientos_cambiados.disconnect(dispatch_uid="test-meses")


def test_dos_saves_seguidos_y_carga_sin_fecha(escenario, senales, django_capture_on_commit_callbacks):
    hogar, _, cuenta, _ = escenario
    octubre, septiembre = date(2026, 10, 1), date(2026, 9, 1)
    MovimientoFactory(cuenta=cuenta, fecha=date(2026, 10, 3))
    m = Movimiento.objects.get()
    with django_capture_on_commit_callbacks(execute=True):
        m.fecha = date(2026, 9, 1)
        m.save()
        m.notas = "solo cambian las notas"
        m.save()  # ya no es octubre: solo septiembre
    assert senales[-2:] == [{octubre, septiembre}, {septiembre}]
    sin_fecha = Movimiento.objects.only("id", "hogar", "notas").get()
    assert sin_fecha.meses_afectados() == {septiembre}  # la fecha diferida se carga al pedirla; no rompe


def test_borrar_una_subcategoria_rearma_la_alerta_de_la_madre(escenario, cliente, django_capture_on_commit_callbacks):
    hogar, roles, cuenta, super_ = escenario
    fruta = CategoriaFactory(hogar=hogar, nombre="Fruta", padre=super_)
    p = Presupuesto.objects.create(hogar=hogar, categoria=super_, mes=date(2026, 10, 1), importe=Decimal("100"))
    MovimientoFactory(cuenta=cuenta, categoria=fruta, fecha=HOY, importe=Decimal("-150"))
    assert comprobar_presupuestos(hogar.pk, [date(2026, 10, 1)]) == [p]  # Súper, superado por su subcategoría
    with django_capture_on_commit_callbacks(execute=True):
        r = cliente(roles["admin"]).delete(f"/api/v1/hogares/{hogar.pk}/categorias/{fruta.pk}/")
    assert r.status_code == 204
    p.refresh_from_db()
    assert p.alerta_enviada is False  # el gasto se queda sin categoría (SET_NULL): Súper ya no está superado


def test_api_de_notificaciones(cliente):
    yo, otro = UsuarioFactory(), UsuarioFactory()
    mias = [Notificacion.objects.create(usuario=yo, tipo=T.TICKET_PROCESADO, titulo=f"n{i}") for i in range(3)]
    ajena = Notificacion.objects.create(usuario=otro, tipo=T.TICKET_PROCESADO, titulo="ajena")
    c = cliente(yo)

    assert [n["titulo"] for n in c.get("/api/v1/notificaciones/").data["results"]] == ["n2", "n1", "n0"]
    assert c.get("/api/v1/notificaciones/no-leidas/").data == {"no_leidas": 3}
    assert c.post(f"/api/v1/notificaciones/{mias[0].pk}/leer/").status_code == 204
    assert c.post(f"/api/v1/notificaciones/{ajena.pk}/leer/").status_code == 404
    assert c.get("/api/v1/notificaciones/", {"leida": "false"}).data["results"][-1]["titulo"] == "n1"
    assert c.post("/api/v1/notificaciones/leer-todas/", {}).data == {"actualizadas": 2}
    assert c.get("/api/v1/notificaciones/no-leidas/").data == {"no_leidas": 0}
    ajena.refresh_from_db()
    assert ajena.leida is False


def test_ticket_websocket_requiere_sesion(api, cliente):
    assert api.post("/api/v1/notificaciones/ws-ticket/").status_code == 401
    r = cliente(UsuarioFactory()).post("/api/v1/notificaciones/ws-ticket/")
    assert r.status_code == 201 and len(r.data["ticket"]) >= 40 and r.data["caduca_en"] == 30
