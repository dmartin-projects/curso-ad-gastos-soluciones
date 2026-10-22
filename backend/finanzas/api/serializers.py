import re
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


def repetido(serializer, modelo, **campos) -> bool:
    """¿Hay otro objeto del hogar con estos valores? Lo que comprueba una UniqueConstraint que incluye `hogar`.

    DRF no la valida porque `hogar` no es un campo del serializer: sin esto, el duplicado llegaría a la base
    de datos y sería un IntegrityError (500) en vez de un error del campo (400).
    """
    otros = modelo.objects.filter(hogar=serializer.context["hogar"], **campos)
    if serializer.instance is not None:
        otros = otros.exclude(pk=serializer.instance.pk)  # al editar, el propio objeto no cuenta
    return otros.exists()


class CuentaSerializer(serializers.ModelSerializer):
    saldo = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)

    class Meta:
        model = Cuenta
        fields = ["id", "nombre", "tipo", "iban", "activa", "saldo"]

    def validate_nombre(self, valor):
        if repetido(self, Cuenta, nombre=valor):
            raise serializers.ValidationError("Ya hay una cuenta con ese nombre.")
        return valor


class CategoriaSerializer(DelHogarMixin, serializers.ModelSerializer):
    campos_del_hogar = {"padre": Categoria}

    class Meta:
        model = Categoria
        fields = ["id", "nombre", "padre", "color", "icono", "orden", "es_ingreso"]

    def validate_color(self, valor):
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", valor):
            raise serializers.ValidationError("El color debe tener el formato #rrggbb.")
        return valor

    def validate(self, datos):
        # En un PATCH, lo que no llega se queda como estaba
        padre = datos["padre"] if "padre" in datos else getattr(self.instance, "padre", None)
        nombre = datos.get("nombre", getattr(self.instance, "nombre", None))
        if padre:
            if self.instance is not None and padre.pk == self.instance.pk:
                raise serializers.ValidationError({"padre": "Una categoría no puede ser su propia madre."})
            if padre.padre_id:
                raise serializers.ValidationError({"padre": "Solo se permiten dos niveles de categorías."})
            if self.instance is not None and self.instance.hijas.exists():
                raise serializers.ValidationError({"padre": "Una categoría con subcategorías no puede colgar de otra."})
        if repetido(self, Categoria, padre=padre, nombre=nombre):
            raise serializers.ValidationError({"nombre": "Ya hay una categoría con ese nombre en este nivel."})
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
    categoria_nombre = serializers.CharField(source="categoria.nombre", read_only=True, default=None, allow_null=True)
    categoria_color = serializers.CharField(source="categoria.color", read_only=True, default=None, allow_null=True)
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

    def validate_importe(self, valor: Decimal) -> Decimal:
        if valor <= 0:
            raise serializers.ValidationError("El importe debe ser mayor que cero.")
        return valor

    def validate_mes(self, valor):
        return valor.replace(day=1)

    def validate(self, datos):
        categoria = datos.get("categoria", getattr(self.instance, "categoria", None))
        mes = datos.get("mes", getattr(self.instance, "mes", None))
        if repetido(self, Presupuesto, categoria=categoria, mes=mes):
            raise serializers.ValidationError({"categoria": "Ya hay un presupuesto de esta categoría para ese mes."})
        return datos


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


class ComparativaDiaSerializer(serializers.Serializer):
    dia = serializers.IntegerField()
    este_mes = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    mes_anterior = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)


class RankingSerializer(serializers.Serializer):
    categoria = serializers.IntegerField()
    nombre = serializers.CharField()
    posicion = serializers.IntegerField(help_text="1 = el mes de más gasto en esa categoría")
    de = serializers.IntegerField(help_text="Meses con gasto en esa categoría (hasta 13)")


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
    comparativa = ComparativaDiaSerializer(many=True)
    ranking = RankingSerializer(many=True)
    evolucion = MesDashboardSerializer(many=True)
    top_comercios = ComercioDashboardSerializer(many=True)
    presupuestos = PresupuestoDashboardSerializer(many=True)
    pendientes_revision = serializers.IntegerField()


class MesQuerySerializer(serializers.Serializer):
    mes = serializers.DateField(input_formats=["%Y-%m"], required=False, help_text="AAAA-MM (por defecto, el actual)")
