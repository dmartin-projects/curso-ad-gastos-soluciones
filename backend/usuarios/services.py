from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.db import transaction
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .tasks import enviar_email_completar_registro, enviar_email_cuenta_existente, enviar_email_recuperacion

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


def registro_pendiente(usuario) -> bool:
    """Cuenta creada por el registro que aún no ha elegido su contraseña."""
    return not usuario.is_active and not usuario.has_usable_password()


def _enviar(tarea, usuario, ruta_front: str) -> None:
    enlace = generar_enlace(usuario, ruta_front)
    transaction.on_commit(lambda: tarea.enqueue(usuario.pk, enlace))  # módulo 26


def solicitar_registro(email: str, **datos) -> None:
    """El registro solo pide el email: la contraseña la elige quien abre el enlace del correo."""
    usuario = Usuario.objects.filter(email__iexact=email).first()
    if usuario is None:
        usuario = Usuario(email=email, is_active=False, **datos)
        usuario.set_unusable_password()  # nadie puede entrar hasta completar el registro
        usuario.save()
    if registro_pendiente(usuario):  # nuevo, o registrado antes sin completar: el mismo correo
        _enviar(enviar_email_completar_registro, usuario, "completar-registro")
    elif usuario.is_active:  # ya tiene cuenta: se lo decimos a él, no a quien rellena el formulario
        _enviar(enviar_email_cuenta_existente, usuario, "nueva-password")
    # Una cuenta desactivada por soporte no recibe nada.


def completar_registro(usuario, password: str) -> None:
    usuario.set_password(password)  # cambia el hash → el enlace deja de valer
    usuario.is_active = True
    usuario.save(update_fields=["password", "is_active"])  # un solo UPDATE: las dos cosas o ninguna


def solicitar_recuperacion(email: str) -> None:
    usuario = Usuario.objects.filter(email__iexact=email).first()
    if usuario is None:
        return
    if registro_pendiente(usuario):  # aún no tiene contraseña que recuperar: le falta elegirla
        _enviar(enviar_email_completar_registro, usuario, "completar-registro")
    elif usuario.is_active:
        _enviar(enviar_email_recuperacion, usuario, "nueva-password")
