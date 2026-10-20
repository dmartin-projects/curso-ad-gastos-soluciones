import django_filters
from django.db.models import Q

from finanzas.models import Categoria, Cuenta, Movimiento


def _del_hogar(modelo):
    def queryset(request):
        vista = request.parser_context["view"] if request else None
        return modelo.objects.filter(hogar=vista.hogar) if vista and not vista.es_esquema() else modelo.objects.none()

    return queryset


class MovimientoFilter(django_filters.FilterSet):
    fecha = django_filters.DateFromToRangeFilter()  # ?fecha_after=&fecha_before=
    importe_min = django_filters.NumberFilter(field_name="importe", lookup_expr="gte")
    importe_max = django_filters.NumberFilter(field_name="importe", lookup_expr="lte")
    cuenta = django_filters.ModelMultipleChoiceFilter(queryset=_del_hogar(Cuenta))
    categoria = django_filters.ModelMultipleChoiceFilter(method="filtrar_categoria", queryset=_del_hogar(Categoria))
    sin_categoria = django_filters.BooleanFilter(field_name="categoria", lookup_expr="isnull")
    tipo = django_filters.ChoiceFilter(choices=[("gasto", "Gastos"), ("ingreso", "Ingresos")], method="filtrar_tipo")
    etiqueta = django_filters.CharFilter(field_name="etiquetas", lookup_expr="contains", method="filtrar_etiqueta")

    class Meta:
        model = Movimiento
        fields = ["fecha", "cuenta", "categoria", "origen", "revisado"]

    @classmethod
    def para_hogar(cls, datos, hogar, queryset):
        """Sin petición (tareas): las opciones de cuenta y categoría se limitan al hogar a mano."""
        filtro = cls(datos, queryset=queryset)
        filtro.filters["cuenta"].queryset = Cuenta.objects.filter(hogar=hogar)
        filtro.filters["categoria"].queryset = Categoria.objects.filter(hogar=hogar)
        return filtro

    def filtrar_categoria(self, qs, name, categorias):
        """Una categoría padre incluye a sus hijas."""
        if not categorias:
            return qs
        return qs.filter(Q(categoria__in=categorias) | Q(categoria__padre__in=categorias))

    def filtrar_tipo(self, qs, name, valor):
        return qs.gastos() if valor == "gasto" else qs.ingresos()

    def filtrar_etiqueta(self, qs, name, valor):
        return qs.filter(etiquetas__contains=[valor.lower()])
