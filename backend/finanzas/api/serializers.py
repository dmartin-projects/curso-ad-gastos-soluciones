from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from finanzas.models import Categoria, Comercio, Cuenta, Movimiento, Presupuesto


class DelHogarMixin:
    """Limita los campos relacionados al hogar de la URL: no se puede apuntar a datos de otro hogar (módulo 33)."""

    campos_del_hogar: dict[str, type] = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hogar = self.context.get("hogar")
        for campo, modelo in self.campos_del_hogar.items():
            if campo in self.fields and hogar is not None:
                self.fields[campo].queryset = modelo.objects.filter(hogar=hogar)


class CuentaSerializer(serializers.ModelSerializer):
    saldo = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Cuenta
        fields = ["id", "nombre", "tipo", "iban", "activa", "saldo"]


class CategoriaSerializer(DelHogarMixin, serializers.ModelSerializer):
    campos_del_hogar = {"padre": Categoria}

    class Meta:
        model = Categoria
        fields = ["id", "nombre", "padre", "color", "icono", "orden", "es_ingreso"]

    def validate(self, datos):
        padre = datos.get("padre")
        if padre and padre.padre_id:
            raise serializers.ValidationError({"padre": "Solo se permiten dos niveles de categorías."})
        return datos


class ReordenarSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False)


class ComercioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Comercio
        fields = ["id", "nombre"]


class MovimientoSerializer(DelHogarMixin, serializers.ModelSerializer):
    campos_del_hogar = {"cuenta": Cuenta, "categoria": Categoria}
    cuenta_nombre = serializers.CharField(source="cuenta.nombre", read_only=True)
    categoria_nombre = serializers.CharField(source="categoria.nombre", read_only=True, default=None)
    categoria_color = serializers.CharField(source="categoria.color", read_only=True, default=None)
    comercio = ComercioSerializer(read_only=True)
    num_adjuntos = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Movimiento
        fields = [
            "id",
            "fecha",
            "importe",
            "concepto",
            "cuenta",
            "cuenta_nombre",
            "categoria",
            "categoria_nombre",
            "categoria_color",
            "comercio",
            "etiquetas",
            "notas",
            "origen",
            "revisado",
            "num_adjuntos",
            "creado",
        ]
        read_only_fields = ["origen", "creado"]

    def validate_importe(self, valor: Decimal) -> Decimal:
        if valor == 0:
            raise serializers.ValidationError("El importe no puede ser cero.")
        return valor

    def validate_fecha(self, valor):
        if valor > timezone.localdate():
            raise serializers.ValidationError("La fecha no puede ser futura.")
        return valor

    def validate_etiquetas(self, valor: list[str]) -> list[str]:
        return sorted({e.strip().lower() for e in valor if e.strip()})


class RecategorizarSerializer(DelHogarMixin, serializers.Serializer):
    campos_del_hogar = {"categoria": Categoria}
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False, max_length=1000)
    categoria = serializers.PrimaryKeyRelatedField(queryset=Categoria.objects.none())


class PresupuestoSerializer(DelHogarMixin, serializers.ModelSerializer):
    campos_del_hogar = {"categoria": Categoria}
    gastado = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    porcentaje = serializers.SerializerMethodField()

    class Meta:
        model = Presupuesto
        fields = ["id", "categoria", "mes", "importe", "gastado", "porcentaje"]

    def get_porcentaje(self, p) -> int | None:
        gastado = getattr(p, "gastado", None)
        return None if gastado is None else int(abs(gastado) / p.importe * 100)

    def validate_mes(self, valor):
        return valor.replace(day=1)


# ── Dashboard (módulo 77): solo salida; documenta la forma en OpenAPI y formatea Decimal y fechas ──
class CategoriaDashboardSerializer(serializers.Serializer):
    categoria = serializers.IntegerField(allow_null=True)
    nombre = serializers.CharField()
    color = serializers.CharField()
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    porcentaje = serializers.DecimalField(max_digits=5, decimal_places=1)


class DiaDashboardSerializer(serializers.Serializer):
    fecha = serializers.DateField()
    gasto = serializers.DecimalField(max_digits=12, decimal_places=2)
    acumulado = serializers.DecimalField(max_digits=12, decimal_places=2)


class MesDashboardSerializer(serializers.Serializer):
    mes = serializers.DateField(format="%Y-%m")
    gastos = serializers.DecimalField(max_digits=12, decimal_places=2)
    ingresos = serializers.DecimalField(max_digits=12, decimal_places=2)


class ComercioDashboardSerializer(serializers.Serializer):
    comercio = serializers.IntegerField()
    nombre = serializers.CharField()
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    veces = serializers.IntegerField()


class PresupuestoDashboardSerializer(serializers.Serializer):
    categoria = serializers.CharField()
    importe = serializers.DecimalField(max_digits=10, decimal_places=2)
    gastado = serializers.DecimalField(max_digits=12, decimal_places=2)
    porcentaje = serializers.IntegerField()


class DashboardSerializer(serializers.Serializer):
    mes = serializers.DateField(format="%Y-%m")
    gastos = serializers.DecimalField(max_digits=12, decimal_places=2)
    ingresos = serializers.DecimalField(max_digits=12, decimal_places=2)
    balance = serializers.DecimalField(max_digits=12, decimal_places=2)
    num_movimientos = serializers.IntegerField()
    gastos_mes_anterior = serializers.DecimalField(max_digits=12, decimal_places=2)
    variacion = serializers.DecimalField(max_digits=7, decimal_places=1, allow_null=True)
    por_categoria = CategoriaDashboardSerializer(many=True)
    acumulado = DiaDashboardSerializer(many=True)
    evolucion = MesDashboardSerializer(many=True)
    top_comercios = ComercioDashboardSerializer(many=True)
    presupuestos = PresupuestoDashboardSerializer(many=True)
    pendientes_revision = serializers.IntegerField()


class MesQuerySerializer(serializers.Serializer):
    mes = serializers.DateField(input_formats=["%Y-%m"], required=False, help_text="AAAA-MM (por defecto, el actual)")
