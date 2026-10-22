from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import serializers

from hogares.models import Hogar, Invitacion, Membresia


class HogarSerializer(serializers.ModelSerializer):
    mi_rol = serializers.CharField(read_only=True)  # anotado en el queryset
    num_miembros = serializers.IntegerField(read_only=True)

    class Meta:
        model = Hogar
        fields = ["id", "nombre", "moneda", "zona_horaria", "mi_rol", "num_miembros", "creado"]
        read_only_fields = ["creado"]

    def validate_zona_horaria(self, valor):
        # El dashboard y los informes hacen ZoneInfo(hogar.zona_horaria): una zona inexistente sería un 500
        try:
            ZoneInfo(valor)
        except (ZoneInfoNotFoundError, ValueError):
            raise serializers.ValidationError("Zona horaria desconocida (p. ej. Europe/Madrid).") from None
        return valor


class MiembroSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="usuario.email", read_only=True)
    nombre = serializers.CharField(source="usuario.get_full_name", read_only=True)

    class Meta:
        model = Membresia
        fields = ["id", "email", "nombre", "rol", "creado"]
        read_only_fields = ["creado"]


class InvitarSerializer(serializers.Serializer):
    email = serializers.EmailField()
    rol = serializers.ChoiceField(choices=Membresia.Rol.choices, default=Membresia.Rol.MIEMBRO)


class InvitacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invitacion
        fields = ["id", "email", "rol", "caduca", "aceptada"]
