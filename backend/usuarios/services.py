from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

Usuario = get_user_model()


def generar_enlace(usuario, ruta_front: str) -> str:
    uid = urlsafe_base64_encode(force_bytes(usuario.pk))
    token = default_token_generator.make_token(usuario)
    return f"{settings.FRONTEND_URL}/{ruta_front}?uid={uid}&token={token}"  # una página de Angular


def usuario_desde_enlace(uid: str, token: str):
    try:
        usuario = Usuario.objects.get(pk=force_str(urlsafe_base64_decode(uid)))
    except (Usuario.DoesNotExist, ValueError, TypeError, OverflowError):
        return None
    return usuario if default_token_generator.check_token(usuario, token) else None
