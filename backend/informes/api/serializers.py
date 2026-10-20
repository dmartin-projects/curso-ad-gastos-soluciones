from django.utils import timezone
from rest_framework import serializers

from informes.models import InformeMensual


class InformeSerializer(serializers.ModelSerializer):
    mes = serializers.DateField(format="%Y-%m", read_only=True)
    periodo = serializers.CharField(read_only=True, help_text="AAAA-MM (mensual) o AAAA (anual): va en la URL")
    automatico = serializers.SerializerMethodField()

    class Meta:
        model = InformeMensual
        fields = ["id", "tipo", "mes", "periodo", "tamano", "automatico", "creado", "actualizado"]
        read_only_fields = fields

    def get_automatico(self, informe) -> bool:
        return informe.generado_por_id is None


class GenerarInformeSerializer(serializers.Serializer):
    tipo = serializers.ChoiceField(choices=InformeMensual.Tipo.choices, default=InformeMensual.Tipo.MENSUAL)
    mes = serializers.DateField(input_formats=["%Y-%m"], help_text="AAAA-MM (en un anual, cualquier mes del año)")
    enviar = serializers.BooleanField(default=False, help_text="Enviarlo también por email a los miembros")

    def validate(self, datos):
        mes = datos["mes"].replace(day=1)
        if datos["tipo"] == InformeMensual.Tipo.ANUAL:
            mes = mes.replace(month=1)
            if mes.year >= timezone.localdate().year:
                raise serializers.ValidationError({"mes": "El informe anual es de un año ya terminado."})
        elif mes > timezone.localdate():
            raise serializers.ValidationError({"mes": "No se puede generar el informe de un mes futuro."})
        return datos | {"mes": mes}


class InformeEncoladoSerializer(serializers.Serializer):
    mes = serializers.CharField()
    estado = serializers.CharField()
