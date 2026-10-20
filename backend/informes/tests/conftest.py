from datetime import date
from decimal import Decimal

import pypdfium2 as pdfium
import pytest

from conftest import CategoriaFactory, CuentaFactory, MovimientoFactory

OCT = date(2026, 10, 1)


def texto_pdf(contenido: bytes) -> str:
    pdf = pdfium.PdfDocument(contenido)
    try:
        return "\n".join(p.get_textpage().get_text_range() for p in pdf)
    finally:
        pdf.close()


@pytest.fixture
def hogar_con_datos(hogar_con_roles):
    hogar, roles = hogar_con_roles
    hogar.nombre = "Piso Ruzafa"
    hogar.save()
    cuenta = CuentaFactory(hogar=hogar, nombre="Común")
    comida = CategoriaFactory(hogar=hogar, nombre="Comida")
    MovimientoFactory(
        cuenta=cuenta, fecha=date(2026, 10, 2), importe=Decimal("-1234.50"), concepto="Muebles", categoria=comida
    )
    MovimientoFactory(cuenta=cuenta, fecha=date(2026, 10, 5), importe=Decimal("-20"), concepto="Cine")
    MovimientoFactory(cuenta=cuenta, fecha=date(2026, 10, 1), importe=Decimal("2000"), concepto="Nómina")
    return hogar, roles
