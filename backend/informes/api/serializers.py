from django.utils import timezone
from rest_framework import serializers

from informes.models import InformeMensual


class InformeSerializer(serializers.ModelSerializer):
    mes = serializers.DateField(format="%Y-%m", read_only=True)
    automatico = serializers.SerializerMethodField()

    class Meta:
        model = InformeMensual
        fields = ["id", "mes", "tamano", "automatico", "creado", "actualizado"]
        read_only_fields = fields

    def get_automatico(self, informe) -> bool:
        return informe.generado_por_id is None


class GenerarInformeSerializer(serializers.Serializer):
    mes = serializers.DateField(input_formats=["%Y-%m"], help_text="AAAA-MM")
    enviar = serializers.BooleanField(default=False, help_text="Enviarlo también por email a los miembros")

    def validate_mes(self, valor):
        if valor > timezone.localdate():
            raise serializers.ValidationError("No se puede generar el informe de un mes futuro.")
        return valor.replace(day=1)


class InformeEncoladoSerializer(serializers.Serializer):
    mes = serializers.CharField()
    estado = serializers.CharField()
