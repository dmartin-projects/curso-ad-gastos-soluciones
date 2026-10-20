from django.contrib.auth import get_user_model, password_validation
from django.db import transaction
from rest_framework import generics, permissions, serializers
from rest_framework.response import Response
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from usuarios.services import generar_enlace, usuario_desde_enlace
from usuarios.tasks import enviar_email_recuperacion, enviar_email_verificacion

from .auth import VistaPublicaAuth
from .serializers import RegistroSerializer, UsuarioSerializer

Usuario = get_user_model()


class Registro(generics.CreateAPIView):
    serializer_class = RegistroSerializer
    permission_classes = [permissions.AllowAny]
    authentication_classes = []
    throttle_scope = "registro"

    def perform_create(self, serializer):
        usuario = serializer.save()
        enlace = generar_enlace(usuario, "verificar-email")
        transaction.on_commit(lambda: enviar_email_verificacion.enqueue(usuario.pk, enlace))  # módulo 26


class VerificarEmail(VistaPublicaAuth):  # base de la sección 4
    def post(self, request, **kwargs):
        usuario = usuario_desde_enlace(request.data.get("uid", ""), request.data.get("token", ""))
        if usuario is None:
            return Response({"detail": "Enlace no válido o caducado."}, status=400)
        usuario.is_active = True
        usuario.save(update_fields=["is_active"])
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
        email = request.data.get("email", "")
        usuario = Usuario.objects.filter(email__iexact=email, is_active=True).first()
        if usuario:
            enlace = generar_enlace(usuario, "nueva-password")
            transaction.on_commit(lambda: enviar_email_recuperacion.enqueue(usuario.pk, enlace))
        # 🔐 misma respuesta exista o no: no reveles qué emails están registrados
        return Response({"detail": "Si el email existe, te hemos enviado un enlace."})


class ConfirmarRecuperacion(VistaPublicaAuth):  # base de la sección 4
    def post(self, request, **kwargs):
        usuario = usuario_desde_enlace(request.data.get("uid", ""), request.data.get("token", ""))
        if usuario is None:
            return Response({"detail": "Enlace no válido o caducado."}, status=400)
        password = request.data.get("password", "")
        password_validation.validate_password(password, user=usuario)  # ValidationError de Django → 400
        usuario.set_password(password)
        usuario.save(update_fields=["password"])  # cambia el hash → el enlace deja de valer
        return Response(status=204)
