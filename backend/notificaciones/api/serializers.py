from rest_framework import serializers

from notificaciones.models import Notificacion


class NotificacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notificacion
        fields = ["id", "tipo", "titulo", "mensaje", "enlace", "hogar", "datos", "leida", "creado"]
        read_only_fields = fields


class LeerSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), required=False, max_length=500)


class TicketWsSerializer(serializers.Serializer):
    ticket = serializers.CharField()
    caduca_en = serializers.IntegerField(help_text="Segundos")
