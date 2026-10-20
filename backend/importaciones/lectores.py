"""Lectura de extractos bancarios: CSV (cualquier banco) y PDF (formato de líneas habitual).

Cada banco exporta a su manera: separador `;` o `,`, codificación UTF-8 o Windows-1252, líneas de
cabecera antes de la tabla, importe en una columna o en dos (cargo/abono), "1.234,56" o "1,234.56"…
Aquí se detecta todo eso y se devuelve siempre lo mismo: una lista de `FilaLeida`.
"""

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import pypdfium2 as pdfium
from openpyxl import load_workbook


class ExtractoNoValido(Exception):
    pass


@dataclass
class FilaLeida:
    numero: int
    fecha: date
    concepto: str
    importe: Decimal
    saldo: Decimal | None = None


@dataclass
class Lectura:
    filas: list[FilaLeida] = field(default_factory=list)
    avisos: list[dict] = field(default_factory=list)

    def aviso(self, linea: int, mensaje: str) -> None:
        self.avisos.append({"linea": linea, "mensaje": mensaje})


@dataclass
class Perfil:
    """Lo que el lector necesita de un `PerfilBanco` (este módulo no depende de Django)."""

    separador: str
    columnas: dict[str, int]  # {"fecha": 0, "concepto": 2, "importe": 3}: posiciones desde 0
    formato_fecha: str
    filas_a_saltar: int = 1  # líneas antes del primer movimiento, cabecera incluida

    def fecha(self, texto: str) -> date:
        try:
            return datetime.strptime(texto.strip(), self.formato_fecha).date()
        except ValueError:
            return parsear_fecha(texto)  # las celdas de fecha de un Excel llegan ya como dd/mm/aaaa


# ── Valores ──
FORMATOS_FECHA = ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%d/%m/%y")


def parsear_fecha(texto: str) -> date:
    texto = texto.strip()
    for formato in FORMATOS_FECHA:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"Fecha no reconocida: {texto!r}")


def parsear_importe(texto: str) -> Decimal:
    """'-1.234,56' · '1,234.56' · '45,3 €' · '(12,00)' · '12,00-' · '−3,10' → Decimal."""
    t = re.sub(r"[\s\xa0€]|EUR", "", texto.strip()).replace("−", "-")
    negativo = t.startswith("-") or t.endswith("-") or (t.startswith("(") and t.endswith(")"))
    t = t.strip("-+()")
    if "," in t and "." in t:  # el separador decimal es el que aparece el último
        miles, decimal = (".", ",") if t.rfind(",") > t.rfind(".") else (",", ".")
    elif "," in t or "." in t:
        sep = "," if "," in t else "."
        # "1.234" o "12,345" (tres cifras tras un único separador) son miles; "45,3" o "45.30", decimales
        miles, decimal = (sep, None) if t.count(sep) > 1 or len(t.rsplit(sep, 1)[1]) == 3 else (None, sep)
    else:
        miles = decimal = None
    if miles:
        t = t.replace(miles, "")
    if decimal:
        t = t.replace(decimal, ".")
    try:
        valor = Decimal(t)
    except InvalidOperation as e:
        raise ValueError(f"Importe no reconocido: {texto!r}") from e
    return -valor if negativo else valor


def _limpiar_concepto(texto: str) -> str:
    return re.sub(r"\s+", " ", texto).strip()[:255]


# ── CSV ──
SINONIMOS = {  # por prioridad: "fecha operación" antes que "fecha valor"
    "fecha": ("fecha operacion", "fecha", "f operacion", "fecha de operacion", "fecha valor", "date"),
    "concepto": ("concepto", "descripcion", "movimiento", "detalle", "concepto comun", "description"),
    "importe": ("importe", "importe eur", "cantidad", "amount"),
    "cargo": ("cargo", "cargos", "debe"),
    "abono": ("abono", "abonos", "haber"),
    "saldo": ("saldo", "balance"),
}


def _clave(texto: str) -> str:
    t = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", t)).strip()


def _columnas(cabecera: list[str]) -> dict[str, int] | None:
    claves = [_clave(c) for c in cabecera]
    columnas = {}
    for campo, sinonimos in SINONIMOS.items():
        for sinonimo in sinonimos:
            if sinonimo in claves:
                columnas[campo] = claves.index(sinonimo)
                break
    tiene_importe = "importe" in columnas or {"cargo", "abono"} <= columnas.keys()
    return columnas if {"fecha", "concepto"} <= columnas.keys() and tiene_importe else None


def _decodificar(contenido: bytes) -> str:
    for codificacion in ("utf-8-sig", "cp1252"):  # cp1252 descodifica casi todo: va la última
        try:
            return contenido.decode(codificacion)
        except UnicodeDecodeError:
            continue
    raise ExtractoNoValido("No se reconoce la codificación del archivo.")


def _buscar_cabecera(filas: list[list[str]]) -> tuple[int, dict[str, int]] | None:
    for i, fila in enumerate(filas[:25]):  # la cabecera puede no estar en la primera línea
        if columnas := _columnas(fila):
            return i, columnas
    return None


NO_ENCONTRADA = (
    "No se encuentran las columnas de fecha, concepto e importe. Crea un perfil de banco y elígelo al subir."
)


def _localizar_cabecera(texto: str) -> tuple[list[list[str]], int, dict[str, int]]:
    """Prueba cada separador: el bueno es el que permite encontrar la cabecera.

    `csv.Sniffer` no sirve aquí: se confunde con las líneas de antes de la tabla (titular, IBAN…),
    que tienen otro número de columnas.
    """
    for separador in (";", ",", "\t", "|"):
        filas = list(csv.reader(io.StringIO(texto), delimiter=separador))
        if encontrada := _buscar_cabecera(filas):
            return filas, *encontrada
    raise ExtractoNoValido(NO_ENCONTRADA)


def _leer_tabla(filas: list[list[str]], inicio: int, columnas: dict[str, int], fecha=parsear_fecha) -> Lectura:
    """Las filas de datos (desde `inicio`, 0-based) ya separadas en celdas: igual para CSV, Excel o perfil."""
    lectura = Lectura()
    for numero, fila in enumerate(filas[inicio:], start=inicio + 1):
        if not any(c.strip() for c in fila):
            continue
        try:
            if "importe" in columnas:
                importe = parsear_importe(fila[columnas["importe"]])
            else:  # dos columnas: cargo (positivo, es un gasto) y abono
                cargo, abono = fila[columnas["cargo"]].strip(), fila[columnas["abono"]].strip()
                importe = -abs(parsear_importe(cargo)) if cargo else parsear_importe(abono)
            saldo = (
                parsear_importe(fila[columnas["saldo"]]) if "saldo" in columnas and fila[columnas["saldo"]] else None
            )
            lectura.filas.append(
                FilaLeida(
                    numero=numero,
                    fecha=fecha(fila[columnas["fecha"]]),
                    concepto=_limpiar_concepto(fila[columnas["concepto"]]),
                    importe=importe,
                    saldo=saldo,
                )
            )
        except (ValueError, IndexError) as e:
            lectura.aviso(numero, f"Fila ignorada: {e}")
    return lectura


def leer_csv(contenido: bytes, perfil: Perfil | None = None) -> Lectura:
    texto = _decodificar(contenido)
    if perfil:  # el usuario ya ha dicho cómo es su banco: nada de adivinar
        filas = list(csv.reader(io.StringIO(texto), delimiter=perfil.separador))
        return _leer_tabla(filas, perfil.filas_a_saltar, perfil.columnas, perfil.fecha)
    filas, i, columnas = _localizar_cabecera(texto)
    return _leer_tabla(filas, i + 1, columnas)


# ── Excel ──
def _texto(valor) -> str:
    """Celda de openpyxl → el mismo texto que tendría en un CSV."""
    if valor is None:
        return ""
    if isinstance(valor, datetime | date):
        return valor.strftime("%d/%m/%Y")
    if isinstance(valor, float):  # 45.3 → "45.30": con 2 decimales, parsear_importe no lo confunde con miles
        return f"{Decimal(repr(valor)).quantize(Decimal('0.01'))}"
    return str(valor)


def leer_xlsx(contenido: bytes, perfil: Perfil | None = None) -> Lectura:
    try:
        # read_only: no carga el libro entero en memoria; data_only: el valor calculado, no la fórmula
        libro = load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    except Exception as e:  # zip dañado, no es un xlsx, xls antiguo…  # noqa: BLE001
        raise ExtractoNoValido("No se puede abrir el Excel. Guárdalo como .xlsx o expórtalo en CSV.") from e
    try:
        filas = [[_texto(c) for c in fila] for fila in libro.worksheets[0].iter_rows(values_only=True)]
    finally:
        libro.close()
    if perfil:
        return _leer_tabla(filas, perfil.filas_a_saltar, perfil.columnas, perfil.fecha)
    if not (encontrada := _buscar_cabecera(filas)):
        raise ExtractoNoValido(NO_ENCONTRADA)
    i, columnas = encontrada
    return _leer_tabla(filas, i + 1, columnas)


# ── PDF ──
FECHA = r"\d{2}/\d{2}/\d{4}"
IMPORTE = r"[-−]?\d{1,3}(?:\.\d{3})*,\d{2}"
INICIO = re.compile(rf"^{FECHA}\s")
COMPLETO = re.compile(rf"\s{IMPORTE}$")
REGISTRO = re.compile(
    rf"^(?P<fecha>{FECHA})\s+(?:{FECHA}\s+)?(?P<concepto>.+?)\s+(?P<importe>{IMPORTE})(?:\s+(?P<saldo>{IMPORTE}))?$"
)


def leer_pdf(contenido: bytes) -> Lectura:
    try:
        pdf = pdfium.PdfDocument(contenido)
    except pdfium.PdfiumError as e:
        raise ExtractoNoValido("El PDF está dañado o protegido con contraseña.") from e
    try:
        texto = "\n".join(pagina.get_textpage().get_text_range() for pagina in pdf)
    finally:
        pdf.close()
    if not texto.strip():
        raise ExtractoNoValido("El PDF no tiene texto (¿es un escaneo?). Descarga el extracto en CSV.")

    # Un movimiento empieza por una fecha y termina con su importe; un concepto largo ocupa varias líneas
    registros: list[list[str]] = []
    for linea in (linea.strip() for linea in texto.splitlines()):
        if INICIO.match(linea):
            registros.append([linea])
        elif registros and linea and not COMPLETO.search(" ".join(registros[-1])):
            registros[-1].append(linea)  # continuación del concepto; cabeceras y pies de página se ignoran

    lectura = Lectura()
    for numero, partes in enumerate(registros, start=1):
        if m := REGISTRO.match(" ".join(partes)):
            lectura.filas.append(
                FilaLeida(
                    numero=numero,
                    fecha=parsear_fecha(m["fecha"]),
                    concepto=_limpiar_concepto(m["concepto"]),
                    importe=parsear_importe(m["importe"]),
                    saldo=parsear_importe(m["saldo"]) if m["saldo"] else None,
                )
            )
        else:
            lectura.aviso(numero, f"No se ha podido leer: {' '.join(partes)[:80]}")
    return lectura


def comprobar_saldos(lectura: Lectura) -> None:
    """Si hay saldo, cada fila debe cuadrar con la anterior: detecta filas mal leídas o que faltan."""
    anterior = None
    for fila in lectura.filas:
        if fila.saldo is None:
            anterior = None
            continue
        if anterior is not None:
            # el extracto puede venir en orden ascendente o descendente
            if fila.saldo != anterior.saldo + fila.importe and anterior.saldo != fila.saldo + anterior.importe:
                lectura.aviso(fila.numero, "El saldo no cuadra con la fila anterior: revisa que no falte ninguna.")
        anterior = fila


def leer(contenido: bytes, formato: str, perfil: Perfil | None = None) -> Lectura:
    if formato == "pdf":
        lectura = leer_pdf(contenido)
    elif formato == "xlsx":
        lectura = leer_xlsx(contenido, perfil)
    else:
        lectura = leer_csv(contenido, perfil)
    comprobar_saldos(lectura)
    return lectura
