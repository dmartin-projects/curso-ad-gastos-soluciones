from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from django.conf import settings
from django.core import mail

from config.celery import app
from conftest import HogarFactory
from informes import services
from informes.models import InformeMensual
from informes.tasks import generar_informes_mensuales
from notificaciones.models import Notificacion

from .conftest import OCT, texto_pdf

pytestmark = pytest.mark.django_db


def test_el_pdf_lleva_el_resumen_y_los_movimientos_agrupados(hogar_con_datos):
    hogar, _ = hogar_con_datos

    contenido = services.pdf(hogar, OCT, idioma="es")

    assert contenido.startswith(b"%PDF-")
    texto = texto_pdf(contenido)
    assert "Informe mensual" in texto and "Octubre 2026" in texto
    assert "Piso Ruzafa · Octubre 2026" in texto  # la cabecera de página (string-set)
    assert "1\xa0254,50 €" in texto  # gastos, con el formato español (separador de miles: espacio duro)
    assert "Muebles" in texto and "Sin categoría" in texto and "Página 1 / 1" in texto


def test_generar_guarda_notifica_y_envia_por_email(hogar_con_datos, django_capture_on_commit_callbacks):
    hogar, roles = hogar_con_datos

    with django_capture_on_commit_callbacks(execute=True):
        informe = services.generar(hogar.pk, OCT)

    assert informe.tamano > 1000 and informe.archivo.name.startswith(f"informes/{hogar.pk}/2026-10-")
    assert Notificacion.objects.filter(tipo="informe_listo").count() == 3  # admin, miembro y lector
    assert len(mail.outbox) == 3
    correo = mail.outbox[0]
    assert correo.subject == "Tu informe de 10/2026 · Piso Ruzafa"
    assert correo.attachments[0][0] == "gastos-2026-10.pdf" and correo.attachments[0][2] == "application/pdf"
    assert "Ver en la app" in correo.alternatives[0][0] and "1\xa0254,50 €" in correo.body


def test_regenerar_reemplaza_el_archivo(hogar_con_datos, django_capture_on_commit_callbacks):
    hogar, _ = hogar_con_datos
    with django_capture_on_commit_callbacks(execute=True):
        primero = services.generar(hogar.pk, OCT, enviar=False)
    viejo = primero.archivo.name
    with django_capture_on_commit_callbacks(execute=True):
        segundo = services.generar(hogar.pk, OCT, enviar=False)

    assert segundo.pk == primero.pk and segundo.archivo.name != viejo
    assert not segundo.archivo.storage.exists(viejo)
    assert len(mail.outbox) == 0


def test_la_tarea_de_beat_genera_el_mes_anterior_una_sola_vez(hogar_con_datos, time_machine):
    hogar, _ = hogar_con_datos
    HogarFactory()  # sin movimientos en octubre: no recibe informe
    time_machine.move_to(datetime(2026, 11, 1, 7, 0, tzinfo=ZoneInfo("Europe/Madrid")))

    assert generar_informes_mensuales() == 1
    assert InformeMensual.objects.get().mes == OCT
    assert generar_informes_mensuales() == 0  # relanzarla no duplica nada


def test_las_tareas_programadas_existen():
    """Un error tipográfico en CELERY_BEAT_SCHEDULE solo se notaría el día 1 a las 7:00…"""
    app.loader.import_default_modules()  # autodiscover_tasks es perezoso: importa los tasks.py como el worker
    for entrada in settings.CELERY_BEAT_SCHEDULE.values():
        assert entrada["task"] in app.tasks


def test_api_generar_listar_y_descargar(hogar_con_datos, cliente, django_capture_on_commit_callbacks):
    hogar, roles = hogar_con_datos
    base = f"/api/v1/hogares/{hogar.pk}/informes/"

    assert cliente(roles["lector"]).post(base, {"mes": "2026-10"}).status_code == 403
    assert cliente(roles["miembro"]).post(base, {"mes": "2999-01"}).status_code == 400
    with django_capture_on_commit_callbacks(execute=True):
        r = cliente(roles["miembro"]).post(base, {"mes": "2026-10"})
    assert r.status_code == 202 and r.data == {"mes": "2026-10", "estado": "generando"}
    assert len(mail.outbox) == 0  # bajo demanda no se envía salvo que se pida

    lector = cliente(roles["lector"])
    assert [i["mes"] for i in lector.get(base).data] == ["2026-10"]
    assert lector.get(base + "2026-10/").data["automatico"] is False
    r = lector.get(base + "2026-10/pdf/")
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf"
    assert r["Content-Disposition"] == 'attachment; filename="gastos-Piso Ruzafa-2026-10.pdf"'
    assert b"".join(r.streaming_content).startswith(b"%PDF-")
    assert lector.get(base + "2026-09/pdf/").status_code == 404
    assert lector.get(base + "2026-13/pdf/").status_code == 404
    assert cliente(roles["ajeno"]).get(base).status_code == 404
