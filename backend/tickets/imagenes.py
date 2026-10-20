import io

from PIL import Image, ImageOps

LADO_MAXIMO = 2500
CALIDAD = 85


def reducir(contenido: bytes) -> bytes | None:
    """JPEG de calidad 85 con el lado mayor ≤ 2500 px, o None si la imagen ya es suficientemente pequeña."""
    with Image.open(io.BytesIO(contenido)) as original:
        if max(original.size) <= LADO_MAXIMO:
            return None
        imagen = ImageOps.exif_transpose(original)  # girar ANTES: al guardar sin EXIF se pierde la orientación
        imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO), Image.Resampling.LANCZOS)  # conserva la proporción
        if imagen.mode not in ("RGB", "L"):
            imagen = imagen.convert("RGB")  # JPEG no admite transparencia (PNG RGBA) ni paleta
        salida = io.BytesIO()
        # Sin exif=…: el EXIF no se copia. De paso desaparecen el GPS y el modelo del móvil (privacidad).
        imagen.save(salida, format="JPEG", quality=CALIDAD, optimize=True)
        return salida.getvalue()
