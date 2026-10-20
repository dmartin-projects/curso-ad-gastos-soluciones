import hashlib
import io
import json
import shutil

import httpx
import pytest
from django.contrib.auth.models import Group
from PIL import Image
from weasyprint import HTML

from conftest import CategoriaFactory, CuentaFactory, HogarFactory, UsuarioFactory
from finanzas.models import Comercio
from finanzas.servicios_comercios import sugerir_categoria
from tickets import ocr
from tickets.models import Ticket

from .conftest import URL_IA, archivo_ticket, datos_ia, imagen_ticket
from .test_api import E, url

pytestmark = pytest.mark.django_db


def respuesta(datos, entrada=812, salida=143):
    cuerpo = {
        "choices": [{"message": {"role": "assistant", "content": json.dumps(datos)}}],
        "usage": {"prompt_tokens": entrada, "completion_tokens": salida, "total_tokens": entrada + salida},
    }
    return httpx.Response(200, json=cuerpo)


@pytest.fixture
def escenario(hogar_con_roles, ocr_falso):
    hogar, roles = hogar_con_roles
    return hogar, roles, CuentaFactory(hogar=hogar), CategoriaFactory(hogar=hogar, nombre="Supermercado")


@pytest.fixture
def subir(cliente, django_capture_on_commit_callbacks):
    def _subir(hogar, usuario, cuenta, archivo=None):
        with django_capture_on_commit_callbacks(execute=True):
            return cliente(usuario).post(
                url(hogar), {"archivo": archivo or archivo_ticket(), "cuenta": cuenta.pk}, format="multipart"
            )

    return _subir


# ── 1. Aprender del usuario ──
def test_confirmar_ensena_al_comercio_y_sirve_a_otros_hogares(escenario, subir, cliente, respx_mock):
    hogar, roles, cuenta, super_ = escenario
    # La IA propone una categoría que el hogar no tiene y duda: el usuario elige "Supermercado"
    respx_mock.post(URL_IA).mock(return_value=respuesta(datos_ia(confianza=0.5, categoria="Alimentación")))
    ticket = Ticket.objects.get(pk=subir(hogar, roles["miembro"], cuenta).data["id"])
    assert ticket.estado == E.REVISAR and ticket.movimiento.categoria is None
    cliente(roles["miembro"]).post(
        url(hogar, f"{ticket.pk}/confirmar/"),
        {"fecha": "2026-10-12", "total": "4.85", "concepto": "Mercadona", "categoria": super_.pk},
    )
    mercadona = Comercio.objects.get(nombre="Mercadona")
    assert mercadona.categoria_sugerida == "Supermercado"

    # Otro hogar, sin historial con Mercadona: lo aprendido gana a lo que diga la IA
    otro = HogarFactory()
    suya = CategoriaFactory(hogar=otro, nombre="supermercado")  # sin distinguir mayúsculas
    assert sugerir_categoria(otro, mercadona, "Otros") == suya


def test_orden_historial_aprendida_ia(escenario):
    from conftest import MovimientoFactory

    hogar, _, cuenta, super_ = escenario
    comida = CategoriaFactory(hogar=hogar, nombre="Comida")
    otros = CategoriaFactory(hogar=hogar, nombre="Otros")
    lidl = Comercio.objects.create(nombre="Lidl", categoria_sugerida="Supermercado")
    assert sugerir_categoria(hogar, lidl, "Otros") == super_  # 2º aprendida, antes que la IA
    MovimientoFactory(cuenta=cuenta, comercio=lidl, categoria=comida)
    assert sugerir_categoria(hogar, lidl, "Otros") == comida  # 1º el historial del hogar
    sin_aprender = Comercio.objects.create(nombre="Bazar")
    assert sugerir_categoria(hogar, sin_aprender, "Otros") == otros  # 3º la IA


def test_lo_aprendido_no_se_sobrescribe(escenario):
    from finanzas.servicios_comercios import aprender_categoria

    hogar, _, _, super_ = escenario
    c = Comercio.objects.create(nombre="Lidl")
    assert aprender_categoria(c, super_) is True
    assert aprender_categoria(c, CategoriaFactory(hogar=hogar, nombre="Ocio")) is False
    c.refresh_from_db()
    assert c.categoria_sugerida == "Supermercado"


# ── 2. Coste: tokens ──
def test_tokens_se_guardan_acumulan_y_salen_en_el_resumen(
    escenario, subir, cliente, respx_mock, django_capture_on_commit_callbacks
):
    hogar, roles, cuenta, _ = escenario
    respx_mock.post(URL_IA).mock(return_value=respuesta(datos_ia(confianza=0.5)))
    ticket = Ticket.objects.get(pk=subir(hogar, roles["miembro"], cuenta).data["id"])
    assert (ticket.tokens_entrada, ticket.tokens_salida) == (812, 143)
    assert "uso" not in ticket.datos_ia  # el consumo no se mezcla con lo extraído

    with django_capture_on_commit_callbacks(execute=True):
        cliente(roles["miembro"]).post(url(hogar, f"{ticket.pk}/reprocesar/"))
    ticket.refresh_from_db()
    assert (ticket.tokens_entrada, ticket.tokens_salida) == (1624, 286)  # reprocesar también cuesta

    personal = UsuarioFactory(is_staff=True)
    personal.groups.add(Group.objects.get(name="Soporte"))
    r = cliente(personal).get("/api/v1/backoffice/resumen/")
    assert r.data["ia_mes"] == {"tickets": 1, "tokens_entrada": 1624, "tokens_salida": 286}


def test_proveedor_sin_usage_no_rompe(escenario, subir, respx_mock):
    hogar, roles, cuenta, _ = escenario
    cuerpo = {"choices": [{"message": {"role": "assistant", "content": json.dumps(datos_ia())}}]}
    respx_mock.post(URL_IA).mock(return_value=httpx.Response(200, json=cuerpo))
    ticket = Ticket.objects.get(pk=subir(hogar, roles["miembro"], cuenta).data["id"])
    assert ticket.estado == E.PROCESADO and ticket.tokens_entrada == 0


# ── 3. Imágenes grandes ──
def foto_grande(ancho=3000, alto=4000, formato="PNG") -> bytes:
    salida = io.BytesIO()
    imagen = Image.new("RGBA" if formato == "PNG" else "RGB", (ancho, alto), "#f4f1ea")
    imagen.paste(Image.open(io.BytesIO(imagen_ticket())), (100, 100))
    imagen.save(salida, format=formato)
    return salida.getvalue()


def test_foto_grande_se_reduce_a_jpeg_y_conserva_la_huella_original(escenario, subir, respx_mock):
    hogar, roles, cuenta, _ = escenario
    respx_mock.post(URL_IA).mock(return_value=respuesta(datos_ia()))
    original = foto_grande()
    r = subir(hogar, roles["miembro"], cuenta, archivo_ticket("grande.png", original, "image/png"))
    ticket = Ticket.objects.get(pk=r.data["id"])

    assert ticket.tipo == "image/jpeg" and ticket.archivo.name.endswith(".jpg")
    with ticket.archivo.open("rb") as f, Image.open(f) as guardada:
        assert guardada.format == "JPEG" and guardada.size == (1875, 2500)  # proporción 3:4 conservada
    assert ticket.huella_archivo == hashlib.sha256(original).hexdigest()

    # Por eso la huella es la del ORIGINAL: volver a subir la misma foto se sigue detectando
    otra = subir(hogar, roles["miembro"], cuenta, archivo_ticket("de-nuevo.png", original, "image/png"))
    assert otra.status_code == 400 and f"ticket {ticket.pk}" in otra.data["errors"]["archivo"][0]


def test_foto_pequena_no_se_toca(escenario, subir, respx_mock):
    hogar, roles, cuenta, _ = escenario
    respx_mock.post(URL_IA).mock(return_value=respuesta(datos_ia()))
    pequena = foto_grande(1200, 1600)
    ticket = Ticket.objects.get(
        pk=subir(hogar, roles["miembro"], cuenta, archivo_ticket("p.png", pequena, "image/png")).data["id"]
    )
    assert ticket.tipo == "image/png"
    with ticket.archivo.open("rb") as f:
        assert f.read() == pequena


def test_reducir_gira_segun_exif_y_quita_el_gps():
    from tickets.imagenes import reducir

    salida = io.BytesIO()
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: girada 90°
    exif[0x8825] = {1: "N", 2: (40.0, 25.0, 0.0)}  # GPSInfo
    Image.new("RGB", (4000, 3000), "white").save(salida, format="JPEG", exif=exif)
    with Image.open(io.BytesIO(reducir(salida.getvalue()))) as r:
        assert r.size == (1875, 2500)  # vertical: el giro se aplicó
        assert not r.getexif()  # ni orientación (ya aplicada) ni GPS


# ── 4. PDF de varias páginas ──
requiere_tesseract = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no está instalado")


def pdf_con_texto(*paginas: str) -> bytes:
    cuerpo = "".join(f'<section style="break-after: page">{p}</section>' for p in paginas)
    return HTML(string=f"<html><body>{cuerpo}</body></html>").write_pdf()


def test_pdf_de_varias_paginas_une_el_texto():
    lectura = ocr.leer_pdf(
        pdf_con_texto(
            "FACTURA 2026/0193 · Ferretería López · NIF B12345678 · Tornillos 3,20",
            "Página dos: Brocas 7,50 · Martillo 12,00 · Base imponible 22,70",
            "TOTAL FACTURA 27,47 EUR · IVA 21 % incluido · Gracias por su compra",
        )
    )
    assert lectura.texto.index("Ferretería") < lectura.texto.index("Brocas") < lectura.texto.index("TOTAL")
    assert "--- Página 3 ---" in lectura.texto
    with Image.open(io.BytesIO(lectura.imagen_png)) as apiladas:
        assert apiladas.height > 3 * apiladas.width  # tres páginas A4 una debajo de otra


@requiere_tesseract
def test_pdf_mixto_texto_y_pagina_escaneada():
    import pypdfium2 as pdfium

    escaneada = io.BytesIO()
    Image.open(io.BytesIO(imagen_ticket())).save(escaneada, format="PDF", resolution=150)
    pdf = pdfium.PdfDocument(pdf_con_texto("Albarán adjunto al ticket de compra, ver página siguiente."))
    pdf.import_pages(pdfium.PdfDocument(escaneada.getvalue()))
    salida = io.BytesIO()
    pdf.save(salida)

    lectura = ocr.leer_pdf(salida.getvalue())
    assert "Albarán" in lectura.texto and "MERCADONA" in lectura.texto  # la 2ª, por OCR


def test_limite_de_paginas(monkeypatch):
    monkeypatch.setattr(ocr, "MAX_PAGINAS", 2)
    lectura = ocr.leer_pdf(
        pdf_con_texto(*[f"Página número {n} con texto suficiente para no ser escaneada" for n in range(5)])
    )
    assert "--- Página 2 ---" in lectura.texto and "--- Página 3 ---" not in lectura.texto
