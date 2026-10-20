# usuarios/api/serializers.py
from django.contrib.auth import get_user_model, password_validation
from rest_framework import serializers

Usuario = get_user_model()


class RegistroSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = Usuario
        fields = ["email", "nombre", "apellidos", "password"]

    def validate_email(self, email):
        return Usuario.objects.normalize_email(email).lower()

    def validate(self, datos):
        # los AUTH_PASSWORD_VALIDATORS de Django (longitud, comunes, parecida al email…)
        password_validation.validate_password(
            datos["password"], user=Usuario(**{k: v for k, v in datos.items() if k != "password"})
        )
        return datos

    def create(self, validated_data):
        return Usuario.objects.create_user(**validated_data, is_active=False)  # activo tras verificar


class UsuarioSerializer(serializers.ModelSerializer):
    es_personal = serializers.BooleanField(source="is_staff", read_only=True)  # el frontend muestra "Soporte"

    class Meta:
        model = Usuario
        fields = ["id", "email", "nombre", "apellidos", "fecha_alta", "es_personal"]
        read_only_fields = ["id", "email", "fecha_alta", "es_personal"]
