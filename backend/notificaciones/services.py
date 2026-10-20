import logging
from datetime import timedelta

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import transaction
from django.utils import timezone, translation

from . import grupos
from .models import Notificacion

logger = logging.getLogger(__name__)


def _enviar(grupo: str, mensaje: dict) -> None:
    """Un fallo de la channel layer (Redis caído) nunca debe romper la operación que avisa."""
    try:
        async_to_sync(get_channel_layer().group_send)(grupo, mensaje)
    except Exception:
        logger.exception("No se pudo enviar al grupo %s", grupo)


def datos_ws(n: Notificacion) -> dict:
    return {
        "id": n.pk,
        "tipo": n.tipo,
        "titulo": n.titulo,
        "mensaje": n.mensaje,
        "enlace": n.enlace,
        "hogar": n.hogar_id,
        "creado": n.creado.isoformat(),
    }


def emitir_a_hogar(hogar_id: int, evento: str, datos: dict | None = None) -> None:
    """Aviso efímero a todos los conectados de un hogar ("algo ha cambiado": refresca)."""
    _enviar(
        grupos.de_hogar(hogar_id),
        {"type": "hogar.evento", "evento": evento, "hogar": hogar_id, "datos": datos or {}},
    )


def emitir_a_usuario(usuario_id: int, tipo: str, datos: dict) -> None:
    _enviar(grupos.de_usuario(usuario_id), {"type": tipo, "datos": datos})


def notificar(usuarios, *, tipo, titulo, mensaje="", contexto=None, hogar=None, enlace="", email=False):
    """Guarda una notificación por usuario, en SU idioma, y la empuja por WebSocket al confirmar la transacción.

    `titulo` y `mensaje` son textos perezosos (gettext_lazy) con marcadores %(nombre)s que se rellenan
    con `contexto`. Se traducen dentro de `translation.override(usuario.idioma)` (RNF7).
    """
    contexto = contexto or {}
    nuevas = []
    for usuario in usuarios:
        with translation.override(usuario.idioma):
            nuevas.append(
                Notificacion(
                    usuario=usuario,
                    hogar=hogar,
                    tipo=tipo,
                    titulo=(str(titulo) % contexto)[:150],
                    mensaje=str(mensaje) % contexto if mensaje else "",
                    enlace=enlace,
                    datos={k: str(v) for k, v in contexto.items()},
                )
            )
    nuevas = Notificacion.objects.bulk_create(nuevas)

    def _al_confirmar():
        for n in nuevas:
            emitir_a_usuario(n.usuario_id, "notificacion.nueva", datos_ws(n))
        if email:
            from .tasks import enviar_email_notificacion

            for n in nuevas:
                if n.tipo not in n.usuario.emails_desactivados:  # la campana siempre; el email, si lo quiere
                    enviar_email_notificacion.enqueue(n.pk)

    transaction.on_commit(_al_confirmar)
    return nuevas


def marcar_leidas(usuario, ids=None) -> int:
    qs = Notificacion.objects.filter(usuario=usuario, leida=False)
    if ids is not None:
        qs = qs.filter(pk__in=ids)
    return qs.update(leida=True, leida_en=timezone.now())


def avisar_cambio_de_grupos(usuario_id: int) -> None:
    """La membresía cambió: el consumer se cierra para que el cliente reconecte con los grupos nuevos."""
    emitir_a_usuario(usuario_id, "grupos.cambiados", {})


def limpiar_leidas(dias: int = 90, lote: int = 5000) -> int:
    """Borra las leídas antiguas por lotes: DELETE … WHERE id IN (SELECT id … LIMIT n), sin traer filas a Python.

    Por lotes para no bloquear la tabla ni generar una transacción enorme si hay millones.
    """
    limite = timezone.now() - timedelta(days=dias)
    total = 0
    while True:
        ids = Notificacion.objects.filter(leida=True, leida_en__lt=limite).values("pk")[:lote]
        # Sin señales ni FKs que apunten a Notificacion, Django hace un "fast delete": una sola consulta
        borradas, _ = Notificacion.objects.filter(pk__in=ids).delete()
        total += borradas
        if borradas < lote:
            return total
