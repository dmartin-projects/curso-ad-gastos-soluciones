import io
import shutil

import pytest
from PIL import Image

from tickets import ocr

from .conftest import imagen_ticket

pytestmark = pytest.mark.skipif(shutil.which("tesseract") is None, reason="Tesseract no está instalado")


def test_lee_una_foto_de_ticket():
    lectura = ocr.leer(imagen_ticket(), "image/jpeg")
    assert "MERCADONA" in lectura.texto
    assert "TOTAL" in lectura.texto and "4,85" in lectura.texto
    assert lectura.es_util


def test_pdf_escaneado_sin_capa_de_texto_pasa_por_el_ocr():
    salida = io.BytesIO()
    Image.open(io.BytesIO(imagen_ticket())).save(salida, format="PDF", resolution=150)
    lectura = ocr.leer(salida.getvalue(), "application/pdf")
    assert "MERCADONA" in lectura.texto


def test_imagen_sin_texto_no_es_util_y_conserva_la_imagen_para_la_ia():
    salida = io.BytesIO()
    Image.new("RGB", (400, 600), "white").save(salida, format="PNG")
    lectura = ocr.leer(salida.getvalue(), "image/png")
    assert not lectura.es_util
    assert lectura.imagen_png.startswith(b"\x89PNG")
