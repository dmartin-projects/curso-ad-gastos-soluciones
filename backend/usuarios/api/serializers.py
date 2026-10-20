# usuarios/api/serializers.py
from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

Usuario = get_user_model()


class RegistroSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    class Meta:
        model = Usuario
        fields = ["email", "nombre", "apellidos", "password"]

    def validate_email(self, email):
        email = Usuario.objects.normalize_email(email).lower()
        # El UniqueValidator del campo compara ANTES de pasar a minúsculas: "Ana@x.com" no choca con
        # "ana@x.com" y el INSERT acabaría en IntegrityError (500). Igual que en el módulo 35.
        if Usuario.objects.filter(email__iexact=email).exists():
            raise serializers.ValidationError("Ya hay una cuenta con ese email.")
        return email

    def validate(self, datos):
        # los AUTH_PASSWORD_VALIDATORS de Django (longitud, comunes, parecida al email…), en el campo password
        sin_password = {k: v for k, v in datos.items() if k != "password"}
        try:
            password_validation.validate_password(datos["password"], user=Usuario(**sin_password))
        except DjangoValidationError as error:
            raise serializers.ValidationError({"password": list(error.messages)}) from error
        return datos

    def create(self, validated_data):
        return Usuario.objects.create_user(**validated_data, is_active=False)  # activo tras verificar


class UsuarioSerializer(serializers.ModelSerializer):
    es_personal = serializers.BooleanField(source="is_staff", read_only=True)  # el frontend muestra "Soporte"

    class Meta:
        model = Usuario
        fields = ["id", "email", "nombre", "apellidos", "fecha_alta", "es_personal"]
        read_only_fields = ["id", "email", "fecha_alta", "es_personal"]
