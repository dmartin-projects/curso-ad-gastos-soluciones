from datetime import date
from decimal import Decimal

import pytest
from django.contrib.postgres.search import TrigramSimilarity
from django.db import IntegrityError, transaction

from conftest import CategoriaFactory, CuentaFactory, MovimientoFactory, UsuarioFactory
from finanzas.models import Categoria, Comercio, Movimiento, Presupuesto
from finanzas.normalizacion import normalizar
from hogares.services import crear_hogar

pytestmark = pytest.mark.django_db


def test_crear_hogar_crea_categorias_por_defecto():
    hogar = crear_hogar(usuario=UsuarioFactory(), nombre="Casa")
    assert hogar.categorias.filter(padre__isnull=True, es_ingreso=False).count() == 9
    assert hogar.categorias.get(nombre="Luz").padre.nombre == "Hogar"
    assert hogar.categorias.filter(es_ingreso=True).count() == 2


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("MERCADONA, S.A. 1234 MADRID", "mercadona madrid"),
        ("Compra tarj. *4321 LIDL SUPERMERCADOS", "lidl supermercados"),
        ("Farmacia Ñandú", "farmacia nandu"),
    ],
)
def test_normalizar(texto, esperado):
    assert normalizar(texto) == esperado


def test_importe_cero_no_permitido():
    with pytest.raises(IntegrityError), transaction.atomic():
        MovimientoFactory(importe=Decimal("0"))


def test_categoria_raiz_duplicada_choca_aunque_padre_sea_null():
    c = CategoriaFactory(nombre="Comida")
    with pytest.raises(IntegrityError), transaction.atomic():
        Categoria.objects.create(hogar=c.hogar, nombre="Comida")


def test_presupuesto_debe_ser_dia_1():
    c = CategoriaFactory()
    with pytest.raises(IntegrityError), transaction.atomic():
        Presupuesto.objects.create(hogar=c.hogar, categoria=c, mes=date(2026, 10, 15), importe=100)


def test_huella_unica_por_cuenta_pero_vacia_permitida():
    cuenta = CuentaFactory()
    MovimientoFactory(cuenta=cuenta, huella="")
    MovimientoFactory(cuenta=cuenta, huella="")  # sin huella (manuales): no chocan
    MovimientoFactory(cuenta=cuenta, huella="abc")
    with pytest.raises(IntegrityError), transaction.atomic():
        MovimientoFactory(cuenta=cuenta, huella="abc")


def test_queryset_del_mes_y_total():
    cuenta = CuentaFactory()
    MovimientoFactory(cuenta=cuenta, fecha=date(2026, 9, 30), importe=Decimal("-10"))
    MovimientoFactory(cuenta=cuenta, fecha=date(2026, 10, 1), importe=Decimal("-20.5"))
    MovimientoFactory(cuenta=cuenta, fecha=date(2026, 10, 31), importe=Decimal("100"))
    octubre = Movimiento.objects.del_hogar(cuenta.hogar).del_mes(date(2026, 10, 1))
    assert octubre.count() == 2
    assert octubre.gastos().total() == Decimal("-20.50")
    assert Movimiento.objects.del_mes(date(2026, 12, 1)).total() == 0


def test_busqueda_trigram_de_comercios():
    for n in ["Mercadona", "Carrefour Express", "Mercado de San Miguel"]:
        Comercio.objects.create(nombre=n)
    mejor = (
        Comercio.objects.annotate(sim=TrigramSimilarity("nombre_normalizado", normalizar("MERCADONA SA 0042")))
        .filter(sim__gt=0.3)
        .order_by("-sim")
        .first()
    )
    assert mejor.nombre == "Mercadona"


def test_adjunto_generico_y_auditoria():
    from django.core.files.base import ContentFile

    from core.auditoria import registrar
    from core.models import Adjunto, RegistroAuditoria

    m = MovimientoFactory(concepto="Cena")
    Adjunto.objects.create(objeto=m, archivo=ContentFile(b"x", name="factura.pdf"), nombre="factura.pdf")
    assert m.adjuntos.count() == 1
    assert Movimiento.objects.filter(adjuntos__nombre="factura.pdf").get() == m  # related_query_name
    from django.forms.models import model_to_dict

    antes = model_to_dict(m)
    m.concepto = "Cena de cumpleaños"
    m.save()
    r = registrar(m, RegistroAuditoria.Accion.MODIFICAR, antes=antes)
    assert r.cambios == {"concepto": ["Cena", "Cena de cumpleaños"]}
    assert r.objeto == m
