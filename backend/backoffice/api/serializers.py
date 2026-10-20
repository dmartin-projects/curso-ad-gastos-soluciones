from django.contrib.auth import get_user_model
from django_celery_beat.models import PeriodicTask
from rest_framework import serializers

from core.models import RegistroAuditoria
from finanzas.models import Movimiento
from hogares.models import Hogar
from importaciones.models import Importacion
from tickets.models import Ticket


class TicketSoporteSerializer(serializers.ModelSerializer):
    hogar_nombre = serializers.CharField(source="hogar.nombre", read_only=True)
    subido_por = serializers.EmailField(source="subido_por.email", read_only=True, default=None)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "hogar",
            "hogar_nombre",
            "subido_por",
            "estado",
            "intentos",
            "confianza",
            "error",
            "nombre_original",
            "creado",
            "actualizado",
        ]
        read_only_fields = fields


class ImportacionSoporteSerializer(serializers.ModelSerializer):
    hogar_nombre = serializers.CharField(source="hogar.nombre", read_only=True)
    progreso = serializers.IntegerField(read_only=True)

    class Meta:
        model = Importacion
        fields = [
            "id",
            "hogar",
            "hogar_nombre",
            "nombre_original",
            "estado",
            "progreso",
            "total_filas",
            "creados",
            "conciliados",
            "duplicados",
            "error",
            "creado",
        ]
        read_only_fields = fields


class HogarSoporteSerializer(serializers.ModelSerializer):
    num_miembros = serializers.IntegerField(read_only=True)
    num_movimientos = serializers.IntegerField(read_only=True)

    class Meta:
        model = Hogar
        fields = ["id", "nombre", "zona_horaria", "num_miembros", "num_movimientos", "creado"]
        read_only_fields = fields


class MiembroSoporteSerializer(serializers.Serializer):
    usuario = serializers.IntegerField(source="usuario_id")
    email = serializers.EmailField(source="usuario.email")
    rol = serializers.CharField()


class HogarDetalleSoporteSerializer(HogarSoporteSerializer):
    miembros = MiembroSoporteSerializer(source="membresias", many=True, read_only=True)

    class Meta(HogarSoporteSerializer.Meta):
        fields = [*HogarSoporteSerializer.Meta.fields, "miembros"]
        read_only_fields = fields


class UsuarioSoporteSerializer(serializers.ModelSerializer):
    class Meta:
        model = get_user_model()
        fields = ["id", "email", "nombre", "apellidos", "is_active", "is_staff", "fecha_alta", "last_login"]
        read_only_fields = ["id", "email", "nombre", "apellidos", "is_staff", "fecha_alta", "last_login"]


class MovimientoSoporteSerializer(serializers.ModelSerializer):
    categoria_nombre = serializers.CharField(source="categoria.nombre", read_only=True, default=None)

    class Meta:
        model = Movimiento
        fields = ["id", "hogar", "fecha", "importe", "concepto", "categoria", "categoria_nombre", "origen", "revisado"]
        read_only_fields = fields


class RecategorizarSoporteSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False, max_length=1000)
    categoria = serializers.IntegerField()


class ResultadoLoteSerializer(serializers.Serializer):
    hechos = serializers.IntegerField()
    omitidos = serializers.IntegerField()


class IdsSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), allow_empty=False, max_length=500)


class AuditoriaSerializer(serializers.ModelSerializer):
    usuario = serializers.EmailField(source="usuario.email", read_only=True, default=None)
    modelo = serializers.SerializerMethodField()

    class Meta:
        model = RegistroAuditoria
        fields = ["id", "fecha", "usuario", "accion", "modelo", "object_id", "representacion", "cambios"]
        read_only_fields = fields

    def get_modelo(self, registro) -> str:
        return f"{registro.content_type.app_label}.{registro.content_type.model}"


class TareaProgramadaSerializer(serializers.ModelSerializer):
    horario = serializers.CharField(source="crontab", read_only=True, default=None)

    class Meta:
        model = PeriodicTask
        fields = ["id", "name", "task", "horario", "enabled", "last_run_at", "total_run_count"]
        read_only_fields = ["id", "name", "task", "horario", "last_run_at", "total_run_count"]


class PorEstadoSerializer(serializers.Serializer):
    clave = serializers.CharField()
    total = serializers.IntegerField()


class IAMesSerializer(serializers.Serializer):
    tickets = serializers.IntegerField()
    tokens_entrada = serializers.IntegerField()
    tokens_salida = serializers.IntegerField()


class ResumenSerializer(serializers.Serializer):
    tickets_24h = PorEstadoSerializer(many=True)
    ia_mes = IAMesSerializer(help_text="Consumo de la IA en el mes en curso (coste)")
    tickets_atascados = serializers.IntegerField()
    importaciones_en_curso = serializers.IntegerField()
    importaciones_con_error_7d = serializers.IntegerField()
    hogares = serializers.IntegerField()
    usuarios_activos = serializers.IntegerField()
