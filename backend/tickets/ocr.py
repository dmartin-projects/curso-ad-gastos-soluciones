"""Lectura del ticket: texto con Tesseract (imágenes) o la capa de texto del PDF.

Todo es local y gratis. Se ejecuta en el worker de la cola "ocr" (CPU), nunca en la petición.
"""

import io
from dataclasses import dataclass

import pypdfium2 as pdfium
import pytesseract
from PIL import Image, ImageOps

MIN_CARACTERES = 40  # por debajo, el OCR no ha leído nada útil
LADO_MINIMO = 1500  # Tesseract lee mal el texto pequeño: se amplía la imagen


@dataclass
class Lectura:
    texto: str
    imagen_png: bytes  # la imagen que se ha leído (por si hay que enviársela a la IA)

    @property
    def es_util(self) -> bool:
        return len(self.texto.strip()) >= MIN_CARACTERES


def _preparar(imagen: Image.Image) -> Image.Image:
    imagen = ImageOps.exif_transpose(imagen)  # fotos del móvil giradas
    imagen = ImageOps.grayscale(imagen)
    imagen = ImageOps.autocontrast(imagen, cutoff=1)
    if (lado := min(imagen.size)) < LADO_MINIMO:
        factor = LADO_MINIMO / lado
        imagen = imagen.resize((round(imagen.width * factor), round(imagen.height * factor)), Image.Resampling.LANCZOS)
    return imagen


def _png(imagen: Image.Image) -> bytes:
    salida = io.BytesIO()
    imagen.save(salida, format="PNG", optimize=True)
    return salida.getvalue()


def leer_imagen(contenido: bytes) -> Lectura:
    with Image.open(io.BytesIO(contenido)) as original:
        imagen = _preparar(original)
    # --psm 4: una columna de texto de tamaños variables (justo un ticket)
    texto = pytesseract.image_to_string(imagen, lang="spa", config="--psm 4", timeout=60)
    return Lectura(texto=texto, imagen_png=_png(imagen))


def leer_pdf(contenido: bytes) -> Lectura:
    pdf = pdfium.PdfDocument(contenido)
    try:
        pagina = pdf[0]
        texto = pagina.get_textpage().get_text_range()  # ticket electrónico: ya trae texto
        imagen = pagina.render(scale=200 / 72).to_pil()  # 200 ppp
        if len(texto.strip()) < MIN_CARACTERES:  # PDF escaneado: no hay capa de texto → OCR
            return leer_imagen(_png(imagen))
        return Lectura(texto=texto, imagen_png=_png(imagen))
    finally:
        pdf.close()


def leer(contenido: bytes, tipo: str) -> Lectura:
    return leer_pdf(contenido) if tipo == "application/pdf" else leer_imagen(contenido)
