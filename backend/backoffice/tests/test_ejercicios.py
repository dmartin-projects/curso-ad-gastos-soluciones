from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group, Permission
from django.core.cache import cache
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from rest_framework_simplejwt.tokens import AccessToken

from backoffice import salud
from conftest import CuentaFactory, HogarFactory, MembresiaFactory, MovimientoFactory, UsuarioFactory
from core.models import RegistroAuditoria
from finanzas.models import Comercio, Movimiento
from tickets.models import Ticket

from .test_backoffice import URL, ticket

pytestmark = pytest.mark.django_db


def personal(cliente, *grupos, permisos=()):
    u = UsuarioFactory(is_staff=True)
    for g in grupos:
        u.groups.add(Group.objects.get(name=g))
    for p in permisos:
        app, codigo = p.split(".")
        u.user_permissions.add(Permission.objects.get(content_type__app_label=app, codename=codigo))
    c = cliente(u)
    c.usuario = u
    return c


# ── 1. Salud de las colas ──
def test_resumen_con_la_salud_de_celery(cliente, monkeypatch):
    llamadas = []

    def falso(timeout=1.0):
        llamadas.append(1)
        return {"workers": 2, "colas": [{"nombre": "ocr", "workers": 1, "pendientes": 7}], "error": ""}

    monkeypatch.setattr(salud, "calcular", falso)
    cache.delete(salud.CLAVE)
    c = personal(cliente, "Soporte")
    for _ in range(3):
        r = c.get(URL + "resumen/")
    assert r.data["celery"]["workers"] == 2 and r.data["celery"]["colas"][0]["pendientes"] == 7
    assert len(llamadas) == 1  # cacheado 30 s: tres visitas, una pregunta al broker


def test_broker_caido_no_tumba_el_resumen(settings):
    from config.celery import app

    app.conf.broker_url = "amqp://nadie:nada@127.0.0.1:1//"  # puerto cerrado
    try:
        datos = salud.calcular(timeout=0.5)
    finally:
        app.conf.broker_url = settings.CELERY_BROKER_URL
    assert datos == {"workers": 0, "colas": [], "error": "No se puede contactar con el broker."}


# ── 2. Fusionar comercios ──
@pytest.fixture
def duplicados(db):
    hogar = HogarFactory()
    cuenta = CuentaFactory(hogar=hogar)
    bueno = Comercio.objects.create(nombre="Mercadona")
    malos = [
        Comercio.objects.create(nombre="MERCADONA S.A. VALENCIA", nif="A46103834"),
        Comercio.objects.create(nombre="Mercadona Online", categoria_sugerida="Supermercado"),
    ]
    for c in [bueno, *malos]:
        MovimientoFactory(cuenta=cuenta, comercio=c, fecha=date(2026, 10, 3), importe=Decimal("-10"))
    return hogar, bueno, malos


def test_fusionar_reasigna_borra_y_audita(cliente, duplicados, django_capture_on_commit_callbacks):
    hogar, bueno, malos = duplicados
    c = personal(cliente, "Soporte")
    with django_capture_on_commit_callbacks(execute=True):
        r = c.post(URL + "comercios/fusionar/", {"origen": [m.pk for m in malos], "destino": bueno.pk})
    assert r.status_code == 200, r.data
    assert r.data == {"reasignados": 2, "borrados": 2}
    assert set(Movimiento.objects.values_list("comercio_id", flat=True)) == {bueno.pk}
    assert not Comercio.objects.filter(pk__in=[m.pk for m in malos]).exists()
    bueno.refresh_from_db()
    assert (bueno.nif, bueno.categoria_sugerida) == ("A46103834", "Supermercado")  # se conserva lo útil
    borrados = RegistroAuditoria.objects.filter(accion="borrar", usuario=c.usuario)
    assert {b.representacion for b in borrados} == {"MERCADONA S.A. VALENCIA", "Mercadona Online"}
    assert RegistroAuditoria.objects.get(accion="modificar", object_id=str(bueno.pk)).cambios["nif"] == [
        "",
        "A46103834",
    ]
    assert c.get(URL + "comercios/", {"search": "mercadona"}).data["results"][0]["num_movimientos"] == 3


def test_fusionar_es_todo_o_nada(cliente, duplicados):
    _, bueno, malos = duplicados
    c = personal(cliente, "Soporte")
    r = c.post(URL + "comercios/fusionar/", {"origen": [malos[0].pk, 999999], "destino": bueno.pk})
    assert r.status_code == 400
    assert Comercio.objects.count() == 3 and Movimiento.objects.filter(comercio=malos[0]).exists()
    r = c.post(URL + "comercios/fusionar/", {"origen": [bueno.pk], "destino": bueno.pk})
    assert r.status_code == 400


def test_fusionar_requiere_permisos(cliente, duplicados):
    _, bueno, malos = duplicados
    c = personal(cliente, "Administración")  # ve usuarios y tareas, no comercios
    assert c.post(URL + "comercios/fusionar/", {"origen": [malos[0].pk], "destino": bueno.pk}).status_code == 403


# ── 3. Suplantar ──
@pytest.fixture
def victima(db):
    u = UsuarioFactory()
    m = MembresiaFactory(usuario=u, rol="admin")
    return u, m.hogar


def test_suplantar_solo_lectura_auditado(cliente, api, victima):
    usuario, hogar = victima
    c = personal(cliente, "Soporte", permisos=["usuarios.suplantar_usuario"])
    r = c.post(f"{URL}usuarios/{usuario.pk}/suplantar/", {"motivo": "No ve sus movimientos de octubre"})
    assert r.status_code == 201 and r.data["caduca_en"] == 300
    token = AccessToken(r.data["access"])
    assert token["user_id"] == str(usuario.pk) and token["suplantado_por"] == c.usuario.pk
    assert token["exp"] - token["iat"] == 300

    api.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")
    assert api.get(f"/api/v1/hogares/{hogar.pk}/movimientos/").status_code == 200  # ve lo que ve el usuario
    r = api.post(f"/api/v1/hogares/{hogar.pk}/cuentas/", {"nombre": "Nueva"})
    assert r.status_code == 403 and "solo lectura" in str(r.data)
    assert api.delete(f"/api/v1/hogares/{hogar.pk}/").status_code == 403

    registro = RegistroAuditoria.objects.get(accion="suplantar")
    assert registro.usuario == c.usuario and registro.object_id == str(usuario.pk)
    assert registro.cambios["motivo"] == "No ve sus movimientos de octubre"


def test_suplantar_cada_peticion_queda_en_el_log(cliente, api, victima, caplog):
    usuario, hogar = victima
    c = personal(cliente, permisos=["usuarios.view_usuario", "usuarios.suplantar_usuario"])
    acceso = c.post(f"{URL}usuarios/{usuario.pk}/suplantar/", {"motivo": "Revisar un error de importación"})
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {acceso.data['access']}")
    with caplog.at_level("INFO", logger="gastos.suplantacion"):
        api.get(f"/api/v1/hogares/{hogar.pk}/dashboard/")
    assert (
        f"personal {c.usuario.pk} como usuario {usuario.pk} → GET /api/v1/hogares/{hogar.pk}/dashboard/" in caplog.text
    )


def test_suplantar_limites(cliente, victima):
    usuario, _ = victima
    sin_permiso = personal(cliente, "Soporte", "Administración")
    assert sin_permiso.post(f"{URL}usuarios/{usuario.pk}/suplantar/", {"motivo": "x" * 20}).status_code == 403
    c = personal(cliente, "Soporte", permisos=["usuarios.suplantar_usuario"])
    assert c.post(f"{URL}usuarios/{usuario.pk}/suplantar/", {"motivo": "corto"}).status_code == 400
    otro_personal = UsuarioFactory(is_staff=True)
    r = c.post(f"{URL}usuarios/{otro_personal.pk}/suplantar/", {"motivo": "Quiero ver su panel"})
    assert r.status_code == 400  # nunca a personal: sería escalar privilegios
    assert c.post(f"{URL}usuarios/{c.usuario.pk}/suplantar/", {"motivo": "A mí mismo, por probar"}).status_code == 400


# ── 4. Grupo Administración ──
def test_grupo_administracion(cliente):
    admin = personal(cliente, "Administración")
    soporte = personal(cliente, "Soporte")
    u = UsuarioFactory()
    tarea = PeriodicTask.objects.create(
        name="prueba", task="core.tasks.limpiar_resultados_de_tareas", crontab=CrontabSchedule.objects.create()
    )

    assert admin.patch(f"{URL}usuarios/{u.pk}/", {"is_active": False}).status_code == 200
    assert soporte.patch(f"{URL}usuarios/{u.pk}/", {"is_active": True}).status_code == 403
    assert admin.patch(f"{URL}tareas/{tarea.pk}/", {"enabled": False}).status_code == 200
    assert soporte.patch(f"{URL}tareas/{tarea.pk}/", {"enabled": True}).status_code == 403
    assert admin.get(URL + "auditoria/").status_code == 200
    # Administración no es soporte: ni tickets ni reprocesar
    t = ticket(huella="z", estado=Ticket.Estado.ERROR)
    assert admin.get(URL + "tickets/").status_code == 403
    assert admin.post(URL + "tickets/reprocesar/", {"ids": [t.pk]}).status_code == 403
    assert not admin.usuario.is_superuser
