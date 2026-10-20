import io
import json

import httpx
import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image, ImageDraw, ImageFont

from tickets import ocr

URL_IA = "https://ia.test/v1/chat/completions"

LINEAS_TICKET = [
    "MERCADONA S.A.",
    "NIF A-46103834",
    "C/ MAYOR 3, VALENCIA",
    "12/10/2026 18:32",
    "LECHE ENTERA 2 x 0,95    1,90",
    "PAN BARRA                0,60",
    "TOMATES                  2,35",
    "TOTAL                    4,85",
]


def imagen_ticket(lineas=LINEAS_TICKET, formato="JPEG") -> bytes:
    """Un ticket «fotografiado» de verdad: texto negro sobre fondo claro."""
    fuente = ImageFont.truetype("DejaVuSansMono.ttf", 36)
    imagen = Image.new("RGB", (900, 90 + 60 * len(lineas)), "#f4f1ea")
    dibujo = ImageDraw.Draw(imagen)
    for i, linea in enumerate(lineas):
        dibujo.text((40, 40 + 60 * i), linea, fill="#111", font=fuente)
    salida = io.BytesIO()
    imagen.save(salida, format=formato)
    return salida.getvalue()


def archivo_ticket(nombre="ticket.jpg", contenido=None, tipo="image/jpeg"):
    return SimpleUploadedFile(nombre, contenido or imagen_ticket(), content_type=tipo)


def datos_ia(**cambios):
    datos = {
        "comercio": "Mercadona",
        "nif": "A46103834",
        "fecha": "2026-10-12",
        "total": 4.85,
        "moneda": "EUR",
        "categoria": "Supermercado",
        "lineas": [
            {"descripcion": "Leche entera", "cantidad": 2, "precio_unitario": 0.95},
            {"descripcion": "Pan barra", "cantidad": 1, "precio_unitario": 0.60},
            {"descripcion": "Tomates", "cantidad": 1, "precio_unitario": 2.35},
        ],
        "confianza": 0.93,
    }
    return datos | cambios


def respuesta_ia(datos) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": json.dumps(datos)}}]})


@pytest.fixture(autouse=True)
def entorno_ia(settings):
    settings.IA_BASE_URL = "https://ia.test/v1/"
    settings.IA_API_KEY = "clave-de-prueba"
    settings.IA_MODELO = "modelo-de-prueba"
    cache.clear()  # el circuit breaker guarda su estado en la caché: cada test empieza con el circuito cerrado


@pytest.fixture
def ocr_falso(monkeypatch):
    """Sustituye Tesseract (lento) en los tests de la API; el OCR real se prueba en test_ocr.py."""

    def _leer(contenido, tipo):
        return ocr.Lectura(texto="\n".join(LINEAS_TICKET), imagen_png=b"")

    monkeypatch.setattr(ocr, "leer", _leer)
