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


MAX_PAGINAS = 10  # una factura larga sí; un PDF de 300 páginas subido por error, no


def _apilar(imagenes: list[Image.Image]) -> Image.Image:
    """Las páginas una debajo de otra: una sola imagen para la IA (el total suele estar en la última)."""
    ancho = max(i.width for i in imagenes)
    lienzo = Image.new("RGB", (ancho, sum(i.height for i in imagenes)), "white")
    y = 0
    for i in imagenes:
        lienzo.paste(i, (0, y))
        y += i.height
    return lienzo


def leer_pdf(contenido: bytes) -> Lectura:
    pdf = pdfium.PdfDocument(contenido)
    try:
        textos, imagenes = [], []
        for n in range(min(len(pdf), MAX_PAGINAS)):
            pagina = pdf[n]
            texto = pagina.get_textpage().get_text_range()  # ticket electrónico: ya trae texto
            imagen = pagina.render(scale=200 / 72).to_pil()  # 200 ppp
            if len(texto.strip()) < MIN_CARACTERES:  # página escaneada: no hay capa de texto → OCR de ESA página
                lectura = leer_imagen(_png(imagen))
                texto, imagen = lectura.texto, Image.open(io.BytesIO(lectura.imagen_png))
            textos.append(texto.strip())
            imagenes.append(imagen)
        # Un separador visible: a la IA le ayuda saber dónde acaba cada página
        texto = (
            "\n\n".join(f"--- Página {n} ---\n{t}" for n, t in enumerate(textos, 1)) if len(textos) > 1 else textos[0]
        )
        return Lectura(texto=texto, imagen_png=_png(_apilar(imagenes[:3]) if len(imagenes) > 1 else imagenes[0]))
    finally:
        pdf.close()


def leer(contenido: bytes, tipo: str) -> Lectura:
    return leer_pdf(contenido) if tipo == "application/pdf" else leer_imagen(contenido)
