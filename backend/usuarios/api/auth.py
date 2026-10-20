# usuarios/api/auth.py
from django.conf import settings
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken


def _poner_cookie_refresh(response, refresh: str):
    cfg = settings.JWT_REFRESH_COOKIE
    response.set_cookie(
        cfg["key"],
        refresh,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        path=cfg["path"],
        httponly=cfg["httponly"],
        secure=cfg["secure"],
        samesite=cfg["samesite"],
    )


class VistaPublicaAuth(APIView):
    """Base para login/refresh/registro: no autentica la petición, pero responde 401 (no 403)."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []  # un access caducado en la cabecera no debe estorbar

    def get_authenticate_header(self, request):
        return 'Bearer realm="api"'


class Login(VistaPublicaAuth):
    throttle_scope = "login"  # 5/min (DEFAULT_THROTTLE_RATES)

    def post(self, request, **kwargs):
        serializer = TokenObtainPairSerializer(data=request.data)  # campos: email (USERNAME_FIELD) y password
        serializer.is_valid(raise_exception=True)  # credenciales malas → 401
        tokens = serializer.validated_data
        response = Response({"access": tokens["access"]})
        _poner_cookie_refresh(response, tokens["refresh"])
        return response


class Refresh(VistaPublicaAuth):
    def post(self, request, **kwargs):
        refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE["key"])
        if not refresh:
            return Response({"detail": "Sin sesión."}, status=status.HTTP_401_UNAUTHORIZED)
        serializer = TokenRefreshSerializer(data={"refresh": refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0]) from exc
        response = Response({"access": serializer.validated_data["access"]})
        _poner_cookie_refresh(response, serializer.validated_data["refresh"])  # rotación
        return response


class Logout(VistaPublicaAuth):
    def post(self, request, **kwargs):
        cfg = settings.JWT_REFRESH_COOKIE
        if refresh := request.COOKIES.get(cfg["key"]):
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                pass  # ya caducado o inválido: da igual
        response = Response(status=status.HTTP_204_NO_CONTENT)
        response.delete_cookie(cfg["key"], path=cfg["path"], samesite=cfg["samesite"])
        return response
