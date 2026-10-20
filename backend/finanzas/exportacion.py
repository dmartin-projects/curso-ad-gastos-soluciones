"""Exportación de movimientos a Excel, fuera de la petición (tarea de Celery)."""

import uuid
from io import BytesIO
from types import SimpleNamespace

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.http import QueryDict
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Font
from rest_framework.exceptions import ValidationError
from rest_framework.filters import UnaccentedSearchFilter

from core.hojas_de_calculo import parece_formula

CABECERA = ["Fecha", "Concepto", "Importe", "Cuenta", "Categoría", "Etiquetas"]
CAMPOS = ("fecha", "concepto", "importe", "cuenta__nombre", "categoria__nombre", "etiquetas")


def ruta(hogar_id: int, archivo: str) -> str:
    return f"exportaciones/{hogar_id}/{archivo}.xlsx"


def filtrar(hogar, params: dict[str, list[str]]):
    """Los mismos filtros y la misma búsqueda que el listado, pero sin petición HTTP (estamos en un worker)."""
    from .api.filters import MovimientoFilter
    from .api.views import MovimientoViewSet
    from .models import Movimiento

    datos = QueryDict(mutable=True)
    for clave, valores in params.items():
        datos.setlist(clave, valores)
    filtro = MovimientoFilter.para_hogar(datos, hogar, queryset=Movimiento.objects.filter(hogar=hogar))
    if not filtro.is_valid():
        raise ValidationError(filtro.errors)
    # SearchFilter solo usa request.query_params y view.search_fields: basta con imitarlos
    return UnaccentedSearchFilter().filter_queryset(SimpleNamespace(query_params=datos), filtro.qs, MovimientoViewSet)


def generar_xlsx(hogar, params: dict[str, list[str]]) -> str:
    """Escribe el .xlsx en el almacenamiento y devuelve su identificador (no adivinable)."""
    libro = Workbook(write_only=True)  # modo streaming: no guarda todas las celdas en memoria
    hoja = libro.create_sheet("Movimientos")
    hoja.freeze_panes = "A2"

    def celda(valor, **estilo):
        c = WriteOnlyCell(hoja, value=valor)
        for k, v in estilo.items():
            setattr(c, k, v)
        return c

    def texto(valor):
        # Texto de terceros: openpyxl guarda como fórmula una cadena que empieza por "=", así que el tipo va explícito
        # ("s": texto). Con quotePrefix, si alguien edita la celda en Excel, sigue siendo texto
        return celda(valor, data_type="s", quotePrefix=parece_formula(valor))

    hoja.append([celda(t, font=Font(bold=True)) for t in CABECERA])
    for fecha, concepto, importe, cuenta, categoria, etiquetas in (
        filtrar(hogar, params).values_list(*CAMPOS).iterator(chunk_size=2000)
    ):
        hoja.append(
            [
                celda(fecha, number_format="DD/MM/YYYY"),  # fecha de verdad, no texto: Excel puede ordenar y filtrar
                texto(concepto),
                celda(importe, number_format="#,##0.00"),  # Decimal → número
                texto(cuenta),
                texto(categoria or ""),
                texto(", ".join(etiquetas)),
            ]
        )
    salida = BytesIO()
    libro.save(salida)
    archivo = uuid.uuid4().hex
    default_storage.save(ruta(hogar.pk, archivo), ContentFile(salida.getvalue()))
    return archivo
