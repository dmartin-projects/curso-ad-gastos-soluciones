from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.utils import timezone
from django_celery_beat.models import CrontabSchedule, PeriodicTask
from rest_framework_simplejwt.tokens import AccessToken

from conftest import CategoriaFactory, CuentaFactory, HogarFactory, MembresiaFactory, MovimientoFactory, UsuarioFactory
from core.models import RegistroAuditoria
from finanzas.models import Movimiento
from tickets.models import Ticket
from tickets.tests.conftest import archivo_ticket

pytestmark = pytest.mark.django_db
URL = "/api/v1/backoffice/"


@pytest.fixture
def soporte(cliente):
    usuario = UsuarioFactory(is_staff=True)
    usuario.groups.add(Group.objects.get(name="Soporte"))  # lo crea post_migrate (core/grupos.py)
    c = cliente(usuario)
    c.usuario = usuario
    return c


@pytest.fixture
def superusuario(cliente):
    return cliente(UsuarioFactory(is_staff=True, is_superuser=True))


def ticket(hogar=None, estado=Ticket.Estado.ERROR, huella="a", **extra):
    hogar = hogar or HogarFactory()
    return Ticket.objects.create(
        hogar=hogar,
        cuenta=CuentaFactory(hogar=hogar),
        archivo=archivo_ticket(),
        huella_archivo=huella,
        estado=estado,
        **extra,
    )


def test_quien_no_es_personal_ni_sabe_que_existe(cliente, api):
    usuario = MembresiaFactory().usuario  # usuario normal, admin de su hogar
    assert cliente(usuario).get(URL + "tickets/").status_code == 404
    assert api.get(URL + "tickets/").status_code == 401


def test_personal_sin_el_permiso_concreto_recibe_403(cliente):
    sin_grupo = cliente(UsuarioFactory(is_staff=True))
    assert sin_grupo.get(URL + "tickets/").status_code == 403


def test_resumen(soporte):
    ticket(huella="a")
    atascado = ticket(huella="b", estado=Ticket.Estado.PROCESANDO)
    Ticket.objects.filter(pk=atascado.pk).update(actualizado=timezone.now() - timedelta(hours=1))
    r = soporte.get(URL + "resumen/")
    assert r.status_code == 200
    assert r.data["tickets_atascados"] == 1
    assert {f["clave"]: f["total"] for f in r.data["tickets_24h"]} == {"error": 1, "procesando": 1}


def test_tickets_de_todos_los_hogares_filtro_atascados_y_reprocesar(soporte, django_capture_on_commit_callbacks):
    con_error = ticket(huella="a")
    procesado = ticket(huella="b", estado=Ticket.Estado.PROCESADO)
    atascado = ticket(huella="c", estado=Ticket.Estado.PENDIENTE)
    Ticket.objects.filter(pk=atascado.pk).update(actualizado=timezone.now() - timedelta(hours=1))

    assert soporte.get(URL + "tickets/").data["count"] == 3  # de cualquier hogar
    assert [t["id"] for t in soporte.get(URL + "tickets/", {"atascado": "true"}).data["results"]] == [atascado.pk]

    with django_capture_on_commit_callbacks() as encolados:  # se encola el OCR, pero no se ejecuta en el test
        r = soporte.post(URL + "tickets/reprocesar/", {"ids": [con_error.pk, procesado.pk]})

    assert r.data == {"hechos": 1, "omitidos": 1}
    con_error.refresh_from_db()
    assert con_error.estado == Ticket.Estado.PENDIENTE and len(encolados) == 1
    registro = RegistroAuditoria.objects.get(object_id=str(con_error.pk))
    assert registro.usuario == soporte.usuario and registro.cambios["estado"] == ["error", "pendiente"]


def test_hogares_con_contadores_y_miembros(soporte, django_assert_max_num_queries):
    m = MembresiaFactory()
    MovimientoFactory.create_batch(3, cuenta=CuentaFactory(hogar=m.hogar))
    HogarFactory.create_batch(5)
    with django_assert_max_num_queries(5):  # sin N+1 aunque haya muchos hogares
        r = soporte.get(URL + "hogares/", {"ordering": "-num_movimientos"})
    assert r.data["results"][0] | {"num_miembros": 1, "num_movimientos": 3} == r.data["results"][0]
    detalle = soporte.get(URL + f"hogares/{m.hogar_id}/").data
    assert detalle["miembros"] == [{"usuario": m.usuario_id, "email": m.usuario.email, "rol": "admin"}]


def test_recategorizar_en_bloque_solo_dentro_del_hogar(soporte, django_capture_on_commit_callbacks):
    cuenta = CuentaFactory()
    destino = CategoriaFactory(hogar=cuenta.hogar)
    mios = MovimientoFactory.create_batch(2, cuenta=cuenta)
    ajeno = MovimientoFactory()
    with django_capture_on_commit_callbacks(execute=True):
        r = soporte.post(
            URL + "movimientos/recategorizar/", {"ids": [*[m.pk for m in mios], ajeno.pk], "categoria": destino.pk}
        )
    assert r.data == {"hechos": 2, "omitidos": 1}
    assert Movimiento.objects.filter(categoria=destino).count() == 2
    registro = RegistroAuditoria.objects.filter(object_id=str(mios[0].pk)).get()
    assert registro.cambios["categoria"][1] == str(destino.pk) and registro.usuario == soporte.usuario


def test_soporte_ve_usuarios_pero_solo_un_superusuario_los_desactiva(soporte, superusuario, api):
    usuario = UsuarioFactory()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(usuario)}")  # un JWT de verdad
    assert api.get("/api/v1/auth/me/").status_code == 200
    assert soporte.get(URL + "usuarios/", {"search": usuario.email}).data["count"] == 1
    assert soporte.patch(URL + f"usuarios/{usuario.pk}/", {"is_active": False}).status_code == 403

    assert superusuario.patch(URL + f"usuarios/{usuario.pk}/", {"is_active": False}).data["is_active"] is False
    assert api.get("/api/v1/auth/me/").status_code == 401  # su access token deja de valer al instante
    registro = RegistroAuditoria.objects.get(object_id=str(usuario.pk))
    assert registro.cambios == {"is_active": ["True", "False"]}  # solo lo que cambió: nunca el hash de la contraseña


def test_la_auditoria_es_de_solo_lectura(soporte):
    soporte.post(URL + "tickets/reprocesar/", {"ids": [ticket().pk]})
    lista = soporte.get(URL + "auditoria/", {"modelo": "tickets.ticket"}).data["results"]
    assert len(lista) == 1 and lista[0]["accion"] == "modificar"
    # DELETE no es una acción de la vista: PermisosPorAccion cierra por defecto (403) antes incluso del 405
    assert soporte.delete(URL + f"auditoria/{lista[0]['id']}/").status_code == 403


def test_pausar_una_tarea_programada(soporte, superusuario):
    tarea = PeriodicTask.objects.create(
        name="informes-mensuales",
        task="informes.tasks.generar_informes_mensuales",
        crontab=CrontabSchedule.objects.create(minute="0", hour="7", day_of_month="1"),
    )
    assert soporte.get(URL + "tareas/").data[0]["name"] == "informes-mensuales"
    assert soporte.patch(URL + f"tareas/{tarea.pk}/", {"enabled": False}).status_code == 403  # Soporte solo mira
    assert superusuario.patch(URL + f"tareas/{tarea.pk}/", {"enabled": False}).data["enabled"] is False


def test_me_dice_si_es_personal(soporte, cliente):
    assert soporte.get("/api/v1/auth/me/").data["es_personal"] is True
    assert cliente(UsuarioFactory()).get("/api/v1/auth/me/").data["es_personal"] is False
