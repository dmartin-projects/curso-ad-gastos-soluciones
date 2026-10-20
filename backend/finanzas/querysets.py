from datetime import date

from django.db import models
from django.db.models import DecimalField, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, TruncMonth


def rango_mes(mes: date) -> tuple[date, date]:
    """(primer día, primer día del mes siguiente)"""
    inicio = mes.replace(day=1)
    fin = date(inicio.year + (inicio.month == 12), inicio.month % 12 + 1, 1)
    return inicio, fin


class MovimientoQuerySet(models.QuerySet):
    def del_hogar(self, hogar):
        return self.filter(hogar=hogar)

    def visibles_para(self, usuario):
        return self.filter(hogar__membresias__usuario=usuario)

    def gastos(self):
        return self.filter(importe__lt=0)

    def ingresos(self):
        return self.filter(importe__gt=0)

    def del_mes(self, mes: date):
        inicio, fin = rango_mes(mes)
        return self.filter(fecha__gte=inicio, fecha__lt=fin)  # rango: usa el índice (no __month)

    def pendientes_revision(self):
        return self.filter(revisado=False)

    def total(self):
        return self.aggregate(t=Coalesce(Sum("importe"), models.Value(0), output_field=models.DecimalField()))["t"]

    def con_detalle(self):
        return self.select_related("cuenta", "categoria", "categoria__padre", "comercio")

    def buscar(self, texto: str):
        return self.filter(
            Q(concepto__icontains=texto) | Q(comercio__nombre__icontains=texto) | Q(notas__icontains=texto)
        )


class PresupuestoQuerySet(models.QuerySet):
    def con_gastado(self):
        """Anota `gastado`: lo gastado (negativo) en el mes del presupuesto, en su categoría y subcategorías.

        Una Subquery correlacionada (módulo 07): una sola consulta para todos los presupuestos.
        """
        from .models import Movimiento

        gastado = (
            Movimiento.objects.gastos()
            .filter(hogar=OuterRef("hogar"))
            .filter(Q(categoria=OuterRef("categoria")) | Q(categoria__padre=OuterRef("categoria")))
            .annotate(m=TruncMonth("fecha"))
            .filter(m=OuterRef("mes"))
            .values("hogar")
            .annotate(t=Sum("importe"))
            .values("t")
        )
        return self.annotate(gastado=Coalesce(Subquery(gastado), Value(0), output_field=DecimalField()))
