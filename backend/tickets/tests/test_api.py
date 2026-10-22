from decimal import Decimal

import httpx
import pytest
from django.core.files.storage import default_storage

from conftest import CategoriaFactory, CuentaFactory, MovimientoFactory
from core.models import RegistroAuditoria
from finanzas.models import Comercio, Movimiento
from tickets.models import Ticket
from tickets.tasks import procesar_ticket

from .conftest import URL_IA, archivo_ticket, datos_ia, imagen_ticket, respuesta_ia

pytestmark = pytest.mark.django_db
E = Ticket.Estado


@pytest.fixture
def escenario(hogar_con_roles, ocr_falso):
    hogar, roles = hogar_con_roles
    cuenta = CuentaFactory(hogar=hogar, nombre="Común")
    super_ = CategoriaFactory(hogar=hogar, nombre="Supermercado")
    return hogar, roles, cuenta, super_


def url(hogar, sufijo=""):
    return f"/api/v1/hogares/{hogar.pk}/tickets/{sufijo}"


@pytest.fixture
def subir(cliente, django_capture_on_commit_callbacks):
    """Sube un ticket ejecutando lo que se encola en on_commit (Celery en modo eager)."""

    def _subir(hogar, usuario, cuenta, archivo=None):
        with django_capture_on_commit_callbacks(execute=True):
            return cliente(usuario).post(
                url(hogar), {"archivo": archivo or archivo_ticket(), "cuenta": cuenta.pk}, format="multipart"
            )

    return _subir


def test_subir_procesa_el_ticket_y_crea_el_gasto(escenario, subir, respx_mock):
    hogar, roles, cuenta, super_ = escenario
    respx_mock.post(URL_IA).mock(return_value=respuesta_ia(datos_ia()))

    r = subir(hogar, roles["miembro"], cuenta)

    assert r.status_code == 202, r.data
    assert r.data["estado"] == E.PENDIENTE  # la respuesta sale antes de procesar
    ticket = Ticket.objects.get(pk=r.data["id"])
    assert ticket.estado == E.PROCESADO and ticket.intentos == 1
    assert ticket.archivo.name.startswith(f"tickets/{hogar.pk}/") and ticket.archivo.name.endswith(".jpg")
    mov = ticket.movimiento
    assert mov.importe == Decimal("-4.85") and mov.origen == Movimiento.Origen.TICKET
    assert mov.revisado and mov.categoria == super_ and mov.comercio.nombre == "Mercadona"
    assert mov.creado_por == roles["miembro"]
    assert [linea.importe for linea in ticket.lineas.all()] == [Decimal("1.90"), Decimal("0.60"), Decimal("2.35")]


def test_la_categoria_habitual_del_hogar_gana_a_la_de_la_ia(escenario, subir, respx_mock):
    hogar, roles, cuenta, _ = escenario
    comida = CategoriaFactory(hogar=hogar, nombre="Comida")
    mercadona = Comercio.objects.create(nombre="MERCADONA S.A.")
    MovimientoFactory.create_batch(2, cuenta=cuenta, comercio=mercadona, categoria=comida)
    respx_mock.post(URL_IA).mock(return_value=respuesta_ia(datos_ia()))

    r = subir(hogar, roles["miembro"], cuenta)

    mov = Ticket.objects.get(pk=r.data["id"]).movimiento
    assert mov.comercio == mercadona  # reconocido por similitud, no duplicado
    assert mov.categoria == comida


def test_a_igualdad_de_veces_la_categoria_sugerida_es_siempre_la_misma(escenario):
    from finanzas.servicios_comercios import sugerir_categoria

    hogar, _, cuenta, _ = escenario
    antigua, nueva = CategoriaFactory(hogar=hogar, nombre="Comida"), CategoriaFactory(hogar=hogar, nombre="Hogar")
    mercadona = Comercio.objects.create(nombre="Mercadona")
    MovimientoFactory(cuenta=cuenta, comercio=mercadona, categoria=nueva)
    MovimientoFactory(cuenta=cuenta, comercio=mercadona, categoria=antigua)
    assert sugerir_categoria(hogar, mercadona) == antigua  # empate a una: desempata el id, no el azar


def test_con_dudas_va_a_revision_y_el_usuario_confirma(escenario, subir, cliente, respx_mock):
    hogar, roles, cuenta, super_ = escenario
    respx_mock.post(URL_IA).mock(return_value=respuesta_ia(datos_ia(confianza=0.55, total=5.85)))

    ticket = Ticket.objects.get(pk=subir(hogar, roles["miembro"], cuenta).data["id"])

    assert ticket.estado == E.REVISAR
    assert "no está segura" in ticket.error and "Las líneas suman 4.85" in ticket.error
    assert ticket.movimiento.revisado is False  # el gasto existe, pero marcado para revisar

    r = cliente(roles["miembro"]).post(
        url(hogar, f"{ticket.pk}/confirmar/"),
        {"fecha": "2026-10-12", "total": "4.85", "concepto": "Mercadona", "categoria": super_.pk},
    )

    assert r.status_code == 200, r.data
    assert r.data["estado"] == E.PROCESADO and r.data["movimiento"]["revisado"] is True
    ticket.movimiento.refresh_from_db()
    assert ticket.movimiento.importe == Decimal("-4.85")
    assert RegistroAuditoria.objects.filter(accion="modificar", object_id=str(ticket.movimiento.pk)).exists()


def test_sin_total_no_hay_gasto_hasta_confirmar(escenario, subir, cliente, respx_mock):
    hogar, roles, cuenta, _ = escenario
    respx_mock.post(URL_IA).mock(return_value=respuesta_ia(datos_ia(total=None, lineas=[])))

    ticket = Ticket.objects.get(pk=subir(hogar, roles["miembro"], cuenta).data["id"])
    assert ticket.estado == E.REVISAR and ticket.movimiento is None

    r = cliente(roles["miembro"]).post(
        url(hogar, f"{ticket.pk}/confirmar/"), {"fecha": "2026-10-12", "total": "12.40", "concepto": "Mercadona"}
    )

    assert r.status_code == 200
    assert Movimiento.objects.get(pk=r.data["movimiento"]["id"]).importe == Decimal("-12.40")


def test_confirmar_no_da_de_alta_comercios_con_el_texto_del_usuario(escenario, subir, cliente, respx_mock):
    hogar, roles, cuenta, _ = escenario
    respx_mock.post(URL_IA).mock(return_value=respuesta_ia(datos_ia(total=None, lineas=[])))
    ticket = Ticket.objects.get(pk=subir(hogar, roles["miembro"], cuenta).data["id"])
    comercios = set(Comercio.objects.values_list("nombre", flat=True))

    r = cliente(roles["miembro"]).post(
        url(hogar, f"{ticket.pk}/confirmar/"),
        {"fecha": "2026-10-12", "total": "3.10", "concepto": "La frutería de Ana"},
    )

    assert r.status_code == 200
    # El catálogo de comercios es global (autocompletado de todos los hogares): el texto libre solo se reconoce
    assert set(Comercio.objects.values_list("nombre", flat=True)) == comercios
    assert Movimiento.objects.get(pk=r.data["movimiento"]["id"]).comercio is None


def test_respuesta_inservible_de_la_ia_pasa_a_revision_sin_reintentar(escenario, subir, respx_mock):
    hogar, roles, cuenta, _ = escenario
    ruta = respx_mock.post(URL_IA).mock(
        return_value=httpx.Response(200, json={"choices": [{"message": {"content": "lo siento"}}]})
    )

    ticket = Ticket.objects.get(pk=subir(hogar, roles["miembro"], cuenta).data["id"])

    assert ticket.estado == E.REVISAR and "JSON" in ticket.error
    assert ruta.call_count == 1


def test_ia_caida_reintenta_abre_el_circuito_y_acaba_en_error(escenario, subir, respx_mock, monkeypatch):
    hogar, roles, cuenta, _ = escenario
    ruta = respx_mock.post(URL_IA).mock(return_value=httpx.Response(503))
    # Con task_eager_propagates=True, un reintento en modo eager lanza Retry en vez de reintentar
    monkeypatch.setitem(procesar_ticket.app.conf, "CELERY_TASK_EAGER_PROPAGATES", False)

    subir(hogar, roles["miembro"], cuenta)

    ticket = Ticket.objects.get()
    assert ticket.estado == E.ERROR and ticket.intentos == 6  # 1 intento + 5 reintentos
    assert ruta.call_count == 5  # el 6º ni siquiera llama: el circuito está abierto
    assert "CircuitoAbierto" in ticket.error


def test_reprocesar_un_ticket_con_error(escenario, cliente, respx_mock, django_capture_on_commit_callbacks):
    hogar, roles, cuenta, _ = escenario
    ticket = Ticket.objects.create(
        hogar=hogar, cuenta=cuenta, archivo=archivo_ticket(), tipo="image/jpeg", huella_archivo="x", estado=E.ERROR
    )
    respx_mock.post(URL_IA).mock(return_value=respuesta_ia(datos_ia()))

    with django_capture_on_commit_callbacks(execute=True):
        r = cliente(roles["miembro"]).post(url(hogar, f"{ticket.pk}/reprocesar/"), {})

    assert r.status_code == 202
    ticket.refresh_from_db()
    assert ticket.estado == E.PROCESADO and ticket.movimiento is not None
    registro = RegistroAuditoria.objects.get(object_id=str(ticket.pk), usuario=roles["miembro"])
    assert registro.cambios["estado"] == ["error", "pendiente"]  # auditado, como desde el backoffice


def test_una_entrega_duplicada_de_la_tarea_no_crea_otro_gasto(escenario, subir, respx_mock):
    hogar, roles, cuenta, _ = escenario
    respx_mock.post(URL_IA).mock(return_value=respuesta_ia(datos_ia()))
    ticket_id = subir(hogar, roles["miembro"], cuenta).data["id"]

    assert procesar_ticket.delay(ticket_id).get() == "omitido"
    assert Movimiento.objects.count() == 1


def test_confirmar_fuera_de_revision_es_409(escenario, cliente):
    hogar, roles, cuenta, _ = escenario
    ticket = Ticket.objects.create(hogar=hogar, cuenta=cuenta, archivo=archivo_ticket(), tipo="image/jpeg")
    r = cliente(roles["miembro"]).post(
        url(hogar, f"{ticket.pk}/confirmar/"), {"fecha": "2026-10-12", "total": "1", "concepto": "x"}
    )
    assert r.status_code == 409 and r.data["type"] == "ticket_estado_no_permitido"


def test_el_mismo_archivo_no_se_sube_dos_veces(escenario, subir, respx_mock):
    hogar, roles, cuenta, _ = escenario
    respx_mock.post(URL_IA).mock(return_value=respuesta_ia(datos_ia()))
    contenido = imagen_ticket()
    primero = subir(hogar, roles["miembro"], cuenta, archivo_ticket(contenido=contenido))

    r = subir(hogar, roles["miembro"], cuenta, archivo_ticket("otro-nombre.jpg", contenido=contenido))

    assert r.status_code == 400
    assert f"ticket {primero.data['id']}" in r.data["errors"]["archivo"][0]


def test_dos_subidas_simultaneas_del_mismo_archivo(escenario, subir, monkeypatch):
    from tickets import services

    hogar, roles, cuenta, _ = escenario
    original = services.subir

    def otra_subida_a_la_vez(**datos):
        # la otra request pasó la misma validación e inserta antes: aquí salta la constraint
        Ticket.objects.create(
            hogar=datos["hogar"],
            cuenta=datos["cuenta"],
            archivo="tickets/otro.jpg",
            nombre_original="otro.jpg",
            tipo=datos["tipo"],
            huella_archivo=datos["huella_archivo"],
        )
        return original(**datos)

    monkeypatch.setattr(services, "subir", otra_subida_a_la_vez)
    r = subir(hogar, roles["miembro"], cuenta)
    assert r.status_code == 400 and r.json()["errors"]["archivo"] == ["Este ticket ya se subió."]  # no un 500


@pytest.mark.parametrize(
    "nombre, contenido, error",
    [
        ("ticket.jpg", b"esto no es una imagen", "Sube una foto"),
        ("ticket.jpg", imagen_ticket()[:300], "dañada"),  # JPEG truncado
        ("ticket.pdf", b"%PDF-1.7\n" + b"0" * (10 * 1024 * 1024), "10 MB"),
    ],
)
def test_valida_el_archivo_por_su_contenido(escenario, cliente, nombre, contenido, error):
    hogar, roles, cuenta, _ = escenario
    r = cliente(roles["miembro"]).post(
        url(hogar), {"archivo": archivo_ticket(nombre, contenido), "cuenta": cuenta.pk}, format="multipart"
    )
    assert r.status_code == 400 and error in r.data["errors"]["archivo"][0]


def test_no_se_puede_usar_una_cuenta_de_otro_hogar(escenario, cliente):
    hogar, roles, _, _ = escenario
    ajena = CuentaFactory()
    r = cliente(roles["miembro"]).post(
        url(hogar), {"archivo": archivo_ticket(), "cuenta": ajena.pk}, format="multipart"
    )
    assert r.status_code == 400 and "cuenta" in r.data["errors"]


@pytest.mark.parametrize("rol, esperado", [("lector", 403), ("ajeno", 404)])
def test_permisos_de_subida(escenario, cliente, rol, esperado):
    hogar, roles, cuenta, _ = escenario
    r = cliente(roles[rol]).post(url(hogar), {"archivo": archivo_ticket(), "cuenta": cuenta.pk}, format="multipart")
    assert r.status_code == esperado


def test_listar_filtrar_ver_archivo_y_borrar(escenario, subir, cliente, respx_mock, django_capture_on_commit_callbacks):
    hogar, roles, cuenta, _ = escenario
    respx_mock.post(URL_IA).mock(return_value=respuesta_ia(datos_ia(confianza=0.4)))
    ticket_id = subir(hogar, roles["miembro"], cuenta).data["id"]
    lector = cliente(roles["lector"])

    assert [t["id"] for t in lector.get(url(hogar), {"estado": "revisar"}).data["results"]] == [ticket_id]
    assert lector.get(url(hogar), {"estado": "procesado"}).data["results"] == []
    enlace = lector.get(url(hogar, f"{ticket_id}/archivo/")).data["url"]
    assert enlace.startswith("http://testserver/media/tickets/")

    nombre = Ticket.objects.get().archivo.name
    with django_capture_on_commit_callbacks(execute=True):
        assert cliente(roles["miembro"]).delete(url(hogar, f"{ticket_id}/")).status_code == 204
    assert not default_storage.exists(nombre)
    assert Movimiento.objects.count() == 1  # el gasto se conserva
