from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics, permissions, serializers
from rest_framework.response import Response
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from usuarios.exceptions import EnlaceNoValido
from usuarios.services import (
    completar_registro,
    registro_pendiente,
    solicitar_recuperacion,
    solicitar_registro,
    usuario_desde_enlace,
)

from .auth import VistaPublicaAuth
from .serializers import RegistroSerializer, UsuarioSerializer


def validar_password(password: str, usuario) -> None:
    """Los AUTH_PASSWORD_VALIDATORS de Django; todos los motivos, en el campo password (400, nunca 500)."""
    try:
        password_validation.validate_password(password, user=usuario)
    except DjangoValidationError as error:
        raise serializers.ValidationError({"password": list(error.messages)}) from error


class Registro(generics.GenericAPIView):
    serializer_class = RegistroSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "registro"

    def post(self, request, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        solicitar_registro(**s.validated_data)
        # 🔐 misma respuesta para un email nuevo, pendiente o con cuenta: no revela cuáles existen
        return Response({"detail": "Revisa tu email: te hemos enviado un enlace para continuar."}, status=202)


class CompletarRegistro(VistaPublicaAuth):  # base de la sección 4
    def post(self, request, **kwargs):
        usuario = usuario_desde_enlace(request.data.get("uid", ""), request.data.get("token", ""))
        if usuario is None or not registro_pendiente(usuario):  # solo completa registros pendientes
            raise EnlaceNoValido()  # formato de error del módulo 38: type "enlace_no_valido"
        password = request.data.get("password", "")
        validar_password(password, usuario)  # una contraseña débil no gasta el enlace: aún no se ha guardado nada
        completar_registro(usuario, password)  # contraseña + activa, a la vez
        return Response(status=204)


class Yo(generics.RetrieveUpdateAPIView):
    serializer_class = UsuarioSerializer

    def get_object(self):
        return self.request.user


class CambiarPasswordSerializer(serializers.Serializer):
    actual = serializers.CharField(write_only=True)
    nueva = serializers.CharField(write_only=True)

    def validate_actual(self, valor):
        if not self.context["request"].user.check_password(valor):
            raise serializers.ValidationError("La contraseña actual no es correcta.")
        return valor

    def validate_nueva(self, valor):
        password_validation.validate_password(valor, user=self.context["request"].user)
        return valor


class CambiarPassword(generics.GenericAPIView):
    serializer_class = CambiarPasswordSerializer

    def post(self, request, **kwargs):
        s = self.get_serializer(data=request.data)
        s.is_valid(raise_exception=True)
        request.user.set_password(s.validated_data["nueva"])
        request.user.save(update_fields=["password"])
        # Opcional: invalidar todos los refresh tokens del usuario (cerrar otras sesiones)
        for t in OutstandingToken.objects.filter(user=request.user):
            BlacklistedToken.objects.get_or_create(token=t)
        return Response(status=204)


class SolicitarRecuperacion(VistaPublicaAuth):  # base de la sección 4
    throttle_scope = "recuperar"

    def post(self, request, **kwargs):
        solicitar_recuperacion(request.data.get("email", ""))
        # 🔐 misma respuesta exista o no: no reveles qué emails están registrados
        return Response({"detail": "Si el email existe, te hemos enviado un enlace."})


class ConfirmarRecuperacion(VistaPublicaAuth):  # base de la sección 4
    def post(self, request, **kwargs):
        usuario = usuario_desde_enlace(request.data.get("uid", ""), request.data.get("token", ""))
        if usuario is None or not usuario.is_active:  # un registro pendiente se completa en completar-registro/
            raise EnlaceNoValido()  # formato de error del módulo 38: type "enlace_no_valido"
        password = request.data.get("password", "")
        validar_password(password, usuario)
        usuario.set_password(password)
        usuario.save(update_fields=["password"])  # cambia el hash → el enlace deja de valer
        return Response(status=204)
