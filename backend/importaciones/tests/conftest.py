from django.core.files.uploadedfile import SimpleUploadedFile
from weasyprint import HTML

# Banco "A": separador ;, Windows-1252, tres líneas antes de la cabecera, importe con signo
CSV_BANCO_A = (
    "Titular;ANA GARCÍA\n"
    "Cuenta;ES12 3456 7890 1234\n"
    "\n"
    "Fecha operación;Fecha valor;Concepto;Importe;Saldo\n"
    "01/10/2026;01/10/2026;COMPRA TARJ. MERCADONA VALENCIA;-45,30;1.954,70\n"
    "02/10/2026;02/10/2026;NÓMINA OCTUBRE ACME SL;2.100,00;4.054,70\n"
    "03/10/2026;04/10/2026;RECIBO IBERDROLA CLIENTES;-61,22;3.993,48\n"
    "05/10/2026;05/10/2026;CAFETERÍA LA PLAZA;-1,50;3.991,98\n"
    "05/10/2026;05/10/2026;CAFETERÍA LA PLAZA;-1,50;3.990,48\n"
).encode("cp1252")

# Banco "B": separador ",", UTF-8 con BOM, fechas ISO, cargo y abono en columnas separadas
CSV_BANCO_B = (
    "﻿Date,Description,Cargo,Abono\n"
    "2026-10-05,CAFETERÍA LA PLAZA,1.50,\n"
    "2026-10-07,BIZUM DE LUIS,,25.00\n"
    '2026-10-08,"AMAZON EU, SARL","1,234.56",\n'
).encode()


def pdf_extracto(filas, pie="Página 1 de 1") -> bytes:
    celdas = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in fila) + "</tr>" for fila in filas)
    html = f"""<h1>Extracto de movimientos</h1><p>Cuenta ES12 3456</p>
    <table style="width: 12cm"><tr><th>Fecha</th><th>F. valor</th><th>Concepto</th><th>Importe</th><th>Saldo</th></tr>
    {celdas}</table><p>{pie}</p>"""
    return HTML(string=html).write_pdf()


def archivo(contenido: bytes, nombre="extracto.csv"):
    return SimpleUploadedFile(nombre, contenido, content_type="text/csv")
