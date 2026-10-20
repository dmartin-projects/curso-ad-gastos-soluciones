# core/hojas_de_calculo.py — texto de terceros en un CSV o un .xlsx sin que se ejecute como fórmula (módulo 73)
#
# CSV injection (OWASP): Excel, LibreOffice y Google Sheets ejecutan como fórmula una celda que empieza por uno de estos
# caracteres (o su versión de ancho completo). El concepto de un extracto del banco o de un ticket lo escribe un
# tercero: "=HYPERLINK(…)" sería un enlace que se lleva datos de la hoja al hacer clic. Solo para celdas de TEXTO: el
# importe "-12,50" es un número y tiene que seguir siéndolo.
FORMULA = ("=", "+", "-", "@", "\t", "\r", "\n", "＝", "＋", "－", "＠")


def parece_formula(valor: str) -> bool:
    return valor.startswith(FORMULA)


def texto_csv(valor: str) -> str:
    """'=HYPERLINK(…)' → "'=HYPERLINK(…)": con el apóstrofo delante, la hoja de cálculo lo abre como texto (según la
    aplicación, el apóstrofo se ve). Las comillas y el separador dentro del campo ya los escapa csv.writer."""
    return f"'{valor}" if parece_formula(valor) else valor
