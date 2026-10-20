from datetime import date
from decimal import Decimal

import pytest

from importaciones.deduplicacion import huellas
from importaciones.lectores import ExtractoNoValido, FilaLeida, leer, parsear_importe

from .conftest import CSV_BANCO_A, CSV_BANCO_B, pdf_extracto


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("-1.234,56", "-1234.56"),
        ("1,234.56", "1234.56"),
        ("45,3 €", "45.3"),
        ("45.30", "45.30"),
        ("1.234", "1234"),
        ("(12,00)", "-12.00"),
        ("12,00-", "-12.00"),
        ("−3,10", "-3.10"),
        ("2.100,00", "2100.00"),
        ("1 234,56 EUR", "1234.56"),
    ],
)
def test_parsear_importe(texto, esperado):
    assert parsear_importe(texto) == Decimal(esperado)


def test_csv_con_cabecera_desplazada_y_windows_1252():
    lectura = leer(CSV_BANCO_A, "csv")
    assert len(lectura.filas) == 5 and lectura.avisos == []
    primera = lectura.filas[0]
    assert (primera.numero, primera.fecha, primera.importe) == (5, date(2026, 10, 1), Decimal("-45.30"))
    assert lectura.filas[1].concepto == "NÓMINA OCTUBRE ACME SL"


def test_csv_con_cargo_y_abono_en_columnas_separadas():
    lectura = leer(CSV_BANCO_B, "csv")
    assert [f.importe for f in lectura.filas] == [Decimal("-1.50"), Decimal("25.00"), Decimal("-1234.56")]
    assert lectura.filas[2].concepto == "AMAZON EU, SARL"


def test_filas_ilegibles_se_avisan_sin_parar_la_importacion():
    contenido = b"Fecha;Concepto;Importe\n01/10/2026;OK;-1,00\n31/02/2026;FECHA IMPOSIBLE;-2,00\n"
    lectura = leer(contenido, "csv")
    assert len(lectura.filas) == 1
    assert lectura.avisos == [{"linea": 3, "mensaje": "Fila ignorada: Fecha no reconocida: '31/02/2026'"}]


def test_csv_sin_columnas_reconocibles():
    with pytest.raises(ExtractoNoValido, match="columnas"):
        leer(b"nombre;edad\nana;30\n", "csv")


def test_pdf_con_conceptos_en_varias_lineas_y_pie_de_pagina():
    contenido = pdf_extracto(
        [
            ("01/10/2026", "01/10/2026", "COMPRA TARJ. MERCADONA VALENCIA CENTRO COMERCIAL", "-45,30", "1.954,70"),
            ("02/10/2026", "02/10/2026", "NOMINA OCTUBRE ACME SL", "2.100,00", "4.054,70"),
        ]
    )
    lectura = leer(contenido, "pdf")
    assert [(f.fecha.day, f.importe, f.saldo) for f in lectura.filas] == [
        (1, Decimal("-45.30"), Decimal("1954.70")),
        (2, Decimal("2100.00"), Decimal("4054.70")),
    ]
    assert lectura.filas[0].concepto == "COMPRA TARJ. MERCADONA VALENCIA CENTRO COMERCIAL"
    assert lectura.avisos == []


def test_el_saldo_delata_una_fila_que_falta():
    contenido = pdf_extracto(
        [
            ("01/10/2026", "01/10/2026", "UNO", "-10,00", "990,00"),
            ("03/10/2026", "03/10/2026", "TRES", "-10,00", "970,00"),  # falta la del día 2
        ]
    )
    assert leer(contenido, "pdf").avisos[0]["linea"] == 2


def test_huellas_estables_y_distintas_para_movimientos_repetidos():
    cafe = FilaLeida(numero=1, fecha=date(2026, 10, 5), concepto="CAFETERÍA LA PLAZA", importe=Decimal("-1.50"))
    otro_cafe = FilaLeida(numero=2, fecha=date(2026, 10, 5), concepto="Cafeteria la Plaza", importe=Decimal("-1.5"))
    primera, segunda = huellas(1, [cafe, otro_cafe])
    assert primera != segunda  # el mismo café dos veces el mismo día: ocurrencias 1 y 2
    assert huellas(1, [cafe]) == [primera]  # otro extracto que solo trae el primero → misma huella
    assert huellas(2, [cafe]) != [primera]  # otra cuenta, otro movimiento
