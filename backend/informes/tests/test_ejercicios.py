import re
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from django.core import mail
from django.template.loader import render_to_string

from conftest import CuentaFactory, HogarFactory, MovimientoFactory, UsuarioFactory
from informes import services
from informes.models import InformeMensual
from informes.tasks import generar_informes_anuales, generar_informes_mensuales

from .conftest import OCT, texto_pdf

pytestmark = pytest.mark.django_db
T = InformeMensual.Tipo


# ── 1. Zona horaria del hogar ──
def hogar_en(zona: str, mes: date) -> HogarFactory:
    hogar = HogarFactory(zona_horaria=zona)
    MovimientoFactory(cuenta=CuentaFactory(hogar=hogar), fecha=mes.replace(day=10))
    return hogar


A, M, L = "Pacific/Auckland", "Europe/Madrid", "America/Los_Angeles"


@pytest.mark.parametrize(
    "ahora_utc, esperados",
    [
        (datetime(2026, 10, 31, 17, 0), set()),  # Auckland: 1 nov 06:00 (UTC+13) → aún no
        (datetime(2026, 10, 31, 18, 0), {A}),  # Auckland: 1 nov 07:00
        (datetime(2026, 11, 1, 5, 0), {A}),  # Madrid: 06:00 → aún no; Auckland sigue en su día 1
        (datetime(2026, 11, 1, 6, 0), {A, M}),  # Madrid: 07:00 (UTC+1 en noviembre)
        (datetime(2026, 11, 1, 11, 0), {M}),  # Auckland: ya es día 2
        (datetime(2026, 11, 1, 15, 0), {M, L}),  # Los Ángeles: 07:00 (UTC−8)
    ],
)
def test_cada_zona_a_sus_7_del_dia_1(time_machine, ahora_utc, esperados):
    for zona in (A, M, L):
        hogar_en(zona, OCT)
    time_machine.move_to(ahora_utc.replace(tzinfo=ZoneInfo("UTC")))
    generar_informes_mensuales()
    assert set(InformeMensual.objects.values_list("hogar__zona_horaria", flat=True)) == esperados
    assert all(i.mes == OCT for i in InformeMensual.objects.all())


def test_un_dia_entero_cubre_todas_las_zonas_una_vez(time_machine):
    for z in ("Pacific/Auckland", "Europe/Madrid", "America/Los_Angeles", "Asia/Kolkata"):  # Kolkata: UTC+5:30
        hogar_en(z, OCT)
    hora = datetime(2026, 10, 31, 0, 0, tzinfo=ZoneInfo("UTC"))
    for h in range(48):  # dos días de ejecuciones horarias
        time_machine.move_to(hora.replace(day=31 if h < 24 else 1, month=10 if h < 24 else 11, hour=h % 24))
        generar_informes_mensuales()
    assert InformeMensual.objects.count() == 4  # cada hogar, una vez


# ── 2. Gráfico SVG ──
def test_el_svg_tiene_24_barras_y_numeros_con_punto(hogar_con_datos):
    hogar, _ = hogar_con_datos
    from django.utils import translation

    with translation.override("es"):
        html = render_to_string("informes/mensual.html", services.contexto(hogar, OCT))
    svg = html[html.index("<svg") : html.index("</svg>")]
    assert svg.count("<rect") == 24 and "10/26" in svg
    # sin {% localize off %}, el español escribiría "12,5" y los atributos dejarían de ser números
    assert not re.search(r'(x|y|width|height)="[0-9]+,[0-9]', svg)


def test_el_pdf_con_grafico_se_genera(hogar_con_datos):
    hogar, _ = hogar_con_datos
    texto = texto_pdf(services.pdf(hogar, OCT, idioma="es"))
    assert "Últimos 12 meses" in texto and "10/26" in texto  # las etiquetas del SVG son texto del PDF


def test_grafico_escala_al_maximo():
    evolucion = [{"mes": date(2026, m, 1), "gastos": Decimal(m * 10), "ingresos": Decimal(0)} for m in range(1, 13)]
    g = services.grafico_evolucion(evolucion, alto=100)
    assert g["barras"][-1]["alto_gasto"] == 100 and g["barras"][0]["alto_gasto"] == pytest.approx(8.3)
    vacio = services.grafico_evolucion([{"mes": OCT, "gastos": Decimal(0), "ingresos": Decimal(0)}])
    assert vacio["barras"][0]["alto_gasto"] == 0  # sin datos: sin dividir por cero


# ── 3. Darse de baja ──
def test_quien_se_da_de_baja_no_recibe_el_informe(hogar_con_datos, django_capture_on_commit_callbacks):
    hogar, roles = hogar_con_datos
    roles["lector"].recibir_informes = False
    roles["lector"].save()
    with django_capture_on_commit_callbacks(execute=True):
        services.generar(hogar.pk, OCT)
    destinatarios = {m.to[0].addr_spec for m in mail.outbox}  # `to` lleva Address (nombre + email, módulo 22)
    assert destinatarios == {roles["admin"].email, roles["miembro"].email}


def test_cabeceras_y_enlace_de_baja_en_un_clic(hogar_con_datos, api, django_capture_on_commit_callbacks):
    hogar, roles = hogar_con_datos
    with django_capture_on_commit_callbacks(execute=True):
        services.generar(hogar.pk, OCT)
    correo = next(m for m in mail.outbox if m.to[0].addr_spec == roles["admin"].email)
    assert correo.extra_headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    url = correo.extra_headers["List-Unsubscribe"].strip("<>")
    assert url.startswith("http") and "/api/v1/informes/baja/" in url
    assert "/baja-informes?token=" in correo.body  # el enlace "humano" del pie, a la página del frontend

    ruta = url[url.index("/api/") :]
    assert api.get(ruta).status_code == 405  # un GET (antivirus, vista previa) no da de baja
    r = api.post(ruta, "List-Unsubscribe=One-Click", content_type="application/x-www-form-urlencoded")
    assert r.status_code == 204  # así lo hace el cliente de correo (RFC 8058): sin sesión ni CSRF
    roles["admin"].refresh_from_db()
    assert roles["admin"].recibir_informes is False
    assert api.post(ruta).status_code == 204  # repetirlo no falla


def test_token_falso_o_de_otro_uso(api):
    from django.core import signing

    u = UsuarioFactory()
    assert api.post("/api/v1/informes/baja/inventado/").status_code == 400
    otro_uso = signing.dumps(u.pk, salt="otra.cosa")  # firmado, pero para otra cosa
    assert api.post(f"/api/v1/informes/baja/{otro_uso}/").status_code == 400
    u.refresh_from_db()
    assert u.recibir_informes is True


# ── 4. Informe anual ──
def test_informe_anual(hogar_con_datos, django_capture_on_commit_callbacks):
    hogar, roles = hogar_con_datos
    cuenta = hogar.cuentas.get()
    MovimientoFactory(cuenta=cuenta, fecha=date(2026, 3, 10), importe=Decimal("-100"), concepto="Marzo")
    MovimientoFactory(cuenta=cuenta, fecha=date(2025, 12, 31), importe=Decimal("-999"))  # otro año: fuera

    with django_capture_on_commit_callbacks(execute=True):
        informe = services.generar(hogar.pk, date(2026, 7, 1), tipo=T.ANUAL)

    assert (informe.tipo, informe.mes, informe.periodo) == (T.ANUAL, date(2026, 1, 1), "2026")
    assert informe.archivo.name.startswith(f"informes/{hogar.pk}/2026-")
    texto = texto_pdf(informe.archivo.read())
    assert "Informe anual" in texto and "Piso Ruzafa · 2026" in texto
    assert "1\xa0354,50 €" in texto  # 1234,50 + 20 + 100 (sin el de 2025)
    assert "Marzo" not in texto or "Octubre" in texto  # la tabla mes a mes
    correo = mail.outbox[0]
    assert correo.subject == "Tu informe anual de 2026 · Piso Ruzafa"
    assert correo.attachments[0][0] == "gastos-2026.pdf"
    # convive con el mensual de enero (misma fecha, otro tipo)
    with django_capture_on_commit_callbacks(execute=True):
        enero = services.generar(hogar.pk, date(2026, 1, 1), enviar=False)
    assert enero.pk != informe.pk


def test_beat_anual_el_2_de_enero(hogar_con_datos, time_machine):
    time_machine.move_to(datetime(2027, 1, 2, 7, 0, tzinfo=ZoneInfo("Europe/Madrid")))
    HogarFactory()  # sin movimientos en 2026
    assert generar_informes_anuales() == 1
    assert InformeMensual.objects.get().periodo == "2026"
    assert generar_informes_anuales() == 0


def test_api_anual(hogar_con_datos, cliente, django_capture_on_commit_callbacks):
    hogar, roles = hogar_con_datos
    base = f"/api/v1/hogares/{hogar.pk}/informes/"
    c = cliente(roles["miembro"])
    from django.utils import timezone

    este_anio = timezone.localdate().year
    assert c.post(base, {"tipo": "anual", "mes": f"{este_anio}-01"}).status_code == 400  # año sin terminar
    with django_capture_on_commit_callbacks(execute=True):
        r = c.post(base, {"tipo": "anual", "mes": f"{este_anio - 1}-06"})
    assert r.status_code == 202 and r.data["mes"] == str(este_anio - 1)
    listado = c.get(base).data
    assert listado[0]["tipo"] == "anual" and listado[0]["periodo"] == str(este_anio - 1)
    r = c.get(f"{base}{este_anio - 1}/pdf/")
    assert r.status_code == 200 and f"-{este_anio - 1}.pdf" in r["Content-Disposition"]
