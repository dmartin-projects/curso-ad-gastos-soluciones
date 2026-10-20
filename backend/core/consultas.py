from django.db.models import Count, IntegerField, OuterRef, Subquery, Value
from django.db.models.functions import Coalesce


def contar(modelo, campo: str):
    """COUNT correlacionado: se calcula solo para las filas de la página, no para toda la tabla.

    Con `annotate(Count("movimientos"))` el GROUP BY con JOIN agregaría TODOS los movimientos de TODOS
    los hogares antes de aplicar el LIMIT de la paginación.
    """
    sub = modelo.objects.filter(**{campo: OuterRef("pk")}).order_by().values(campo).annotate(n=Count("pk")).values("n")
    return Coalesce(Subquery(sub, output_field=IntegerField()), Value(0))
