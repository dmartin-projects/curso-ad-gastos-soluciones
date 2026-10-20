import re
import unicodedata

# Ruido típico de conceptos bancarios y tickets (se aplica DESPUÉS de quitar la puntuación)
_RUIDO = re.compile(
    r"\b(s a u|s l u|s a|s l|sau|slu|sa|sl|sociedad|compra|tarj|tarjeta|pago|cargo|recibo|ref|n|\d{4,}|www|com|es)\b"
)


def normalizar(texto: str) -> str:
    """'MERCADONA, S.A. 1234 MADRID' → 'mercadona madrid' (minúsculas, sin acentos, sin ruido)."""
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = _RUIDO.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()
