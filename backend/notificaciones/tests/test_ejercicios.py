from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.utils import timezone

from conftest import CategoriaFactory, CuentaFactory, MovimientoFactory, UsuarioFactory
from finanzas.models import Movimiento, Presupuesto
from finanzas.servicios_presupuestos import comprobar_presupuestos
from finanzas.signals import movimientos_cambiados
from notificaciones.models import Notificacion
from notificaciones.services import limpiar_leidas, notificar
from notificaciones.tasks import limpiar_notificaciones_leidas

pytestmark = pytest.mark.django_db
T = Notificacion.Tipo
OCTUBRE, SEPTIEMBRE = date(2026, 10, 1), date(2026, 9, 1)


@pytest.fixture
def escenario(hogar_con_roles):
    hogar, roles = hogar_con_roles
    return hogar, roles, CuentaFactory(hogar=hogar), CategoriaFactory(hogar=hogar, nombre="Súper")


# ── 1. Preferencias de email ──
def test_preferencias_api_y_validacion(cliente):
    u = UsuarioFactory()
    c = cliente(u)
    assert c.get("/api/v1/notificaciones/preferencias/").data == {"emails_desactivados": [], "recibir_informes": True}
    r = c.put(
        "/api/v1/notificaciones/preferencias/",
        {"emails_desactivados": ["presupuesto_80", "presupuesto_80", "informe_listo"], "recibir_informes": True},
        format="json",
    )
    assert r.data["emails_desactivados"] == ["informe_listo", "presupuesto_80"]  # sin repetidos
    u.refresh_from_db()
    assert u.emails_desactivados == ["informe_listo", "presupuesto_80"]
    r = c.put(
        "/api/v1/notificaciones/preferencias/",
        {"emails_desactivados": ["spam"], "recibir_informes": True},
        format="json",
    )
    assert r.status_code == 400


def test_notificar_respeta_las_preferencias(django_capture_on_commit_callbacks):
    quiere, no_quiere = UsuarioFactory(), UsuarioFactory(emails_desactivados=[T.PRESUPUESTO_SUPERADO])
    with django_capture_on_commit_callbacks(execute=True):
        notificar([quiere, no_quiere], tipo=T.PRESUPUESTO_SUPERADO, titulo="Aviso", email=True)
    assert Notificacion.objects.count() == 2  # la campana, siempre
    assert [m.to for m in mail.outbox] == [[quiere.email]]  # el email, solo a quien lo quiere


# ── 2. Aviso al 80 % ──
def test_aviso_al_80_una_vez_y_despues_superado(escenario):
    hogar, _, cuenta, super_ = escenario
    p = Presupuesto.objects.create(hogar=hogar, categoria=super_, mes=OCTUBRE, importe=Decimal("100"))

    def gastar(importe):
        MovimientoFactory(cuenta=cuenta, categoria=super_, fecha=date(2026, 10, 5), importe=Decimal(importe))
        comprobar_presupuestos(hogar.pk, [OCTUBRE])

    gastar("-70")
    assert not Notificacion.objects.exists()
    gastar("-15")  # 85 %
    avisos = Notificacion.objects.filter(tipo=T.PRESUPUESTO_80)
    assert avisos.count() == 3 and avisos[0].titulo == "Presupuesto de Súper al 85 %"
    gastar("-5")  # 90 %: ya avisado
    assert avisos.count() == 3
    gastar("-20")  # 110 %: ahora "superado", y el del 80 % no se repite
    assert Notificacion.objects.filter(tipo=T.PRESUPUESTO_SUPERADO).count() == 3 and avisos.count() == 3
    p.refresh_from_db()
    assert p.aviso_enviado and p.alerta_enviada


def test_de_golpe_al_120_solo_avisa_de_superado(escenario):
    hogar, _, cuenta, super_ = escenario
    Presupuesto.objects.create(hogar=hogar, categoria=super_, mes=OCTUBRE, importe=Decimal("100"))
    MovimientoFactory(cuenta=cuenta, categoria=super_, fecha=date(2026, 10, 5), importe=Decimal("-120"))
    comprobar_presupuestos(hogar.pk, [OCTUBRE])
    assert set(Notificacion.objects.values_list("tipo", flat=True)) == {T.PRESUPUESTO_SUPERADO}


def test_el_aviso_del_80_se_rearma(escenario):
    hogar, _, cuenta, super_ = escenario
    p = Presupuesto.objects.create(hogar=hogar, categoria=super_, mes=OCTUBRE, importe=Decimal("100"))
    gasto = MovimientoFactory(cuenta=cuenta, categoria=super_, fecha=date(2026, 10, 5), importe=Decimal("-85"))
    comprobar_presupuestos(hogar.pk, [OCTUBRE])
    gasto.delete()
    comprobar_presupuestos(hogar.pk, [OCTUBRE])
    p.refresh_from_db()
    assert p.aviso_enviado is False


# ── 3. Limpieza ──
def test_limpieza_borra_solo_leidas_antiguas_en_una_consulta_por_lote(django_assert_num_queries):
    u = UsuarioFactory()
    ahora = timezone.now()

    def n(leida, hace_dias):
        return Notificacion(
            usuario=u,
            tipo=T.INFORME_LISTO,
            titulo="x",
            leida=leida,
            leida_en=ahora - timedelta(days=hace_dias) if leida else None,
        )

    Notificacion.objects.bulk_create([n(True, 100)] * 5 + [n(True, 30), n(False, 0)])
    # lote de 2 → 3 DELETE (2 + 2 + 1); cada uno es UNA consulta: nada de SELECT previo ni de objetos en memoria
    with django_assert_num_queries(3):
        assert limpiar_leidas(dias=90, lote=2) == 5
    assert Notificacion.objects.count() == 2


def test_limpieza_esta_en_beat(settings):
    assert any(
        t["task"] == "notificaciones.tasks.limpiar_notificaciones_leidas"
        for t in settings.CELERY_BEAT_SCHEDULE.values()
    )
    assert limpiar_notificaciones_leidas() == 0


# ── 4. Cambio de mes ──
@pytest.fixture
def senales():
    recibidas = []

    def receptor(sender, hogar_id, meses, **kwargs):
        recibidas.append(meses)

    movimientos_cambiados.connect(receptor, dispatch_uid="test-meses")
    yield recibidas
    movimientos_cambiados.disconnect(dispatch_uid="test-meses")


def test_mover_un_gasto_de_mes_avisa_de_los_dos(escenario, cliente, senales, django_capture_on_commit_callbacks):
    hogar, roles, cuenta, _ = escenario
    m = MovimientoFactory(cuenta=cuenta, fecha=date(2026, 10, 3))
    senales.clear()
    with django_capture_on_commit_callbacks(execute=True):
        r = cliente(roles["miembro"]).patch(f"/api/v1/hogares/{hogar.pk}/movimientos/{m.pk}/", {"fecha": "2026-09-28"})
    assert r.status_code == 200
    assert senales == [{OCTUBRE, SEPTIEMBRE}]


def test_presupuesto_del_mes_anterior_se_rearma_al_sacar_el_gasto(escenario, django_capture_on_commit_callbacks):
    hogar, _, cuenta, super_ = escenario
    p = Presupuesto.objects.create(hogar=hogar, categoria=super_, mes=OCTUBRE, importe=Decimal("100"))
    m = MovimientoFactory(cuenta=cuenta, categoria=super_, fecha=date(2026, 10, 3), importe=Decimal("-150"))
    comprobar_presupuestos(hogar.pk, [OCTUBRE])
    m = Movimiento.objects.get(pk=m.pk)  # cargado desde la BD: from_db guarda la fecha
    m.fecha = date(2026, 9, 28)
    with django_capture_on_commit_callbacks(execute=True):
        m.save()  # señal → comprobar presupuestos (agrupado) de AMBOS meses
    p.refresh_from_db()
    assert p.alerta_enviada is False  # sin el mes original, octubre se quedaría "superado" para siempre


def test_dos_saves_seguidos_y_carga_sin_fecha(escenario, senales, django_capture_on_commit_callbacks):
    hogar, _, cuenta, _ = escenario
    MovimientoFactory(cuenta=cuenta, fecha=date(2026, 10, 3))
    m = Movimiento.objects.get()
    with django_capture_on_commit_callbacks(execute=True):
        m.fecha = date(2026, 9, 1)
        m.save()
        m.notas = "solo cambian las notas"
        m.save()  # ya no es octubre: solo septiembre
    assert senales[-2:] == [{OCTUBRE, SEPTIEMBRE}, {SEPTIEMBRE}]
    sin_fecha = Movimiento.objects.only("id", "hogar", "notas").get()
    assert sin_fecha.meses_afectados() == {SEPTIEMBRE}  # la fecha diferida se carga al pedirla; no rompe
