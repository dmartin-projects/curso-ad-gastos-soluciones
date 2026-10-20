import secrets
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache

DURACION_TICKET = 30  # segundos


def crear_ticket(usuario) -> str:
    """Un ticket de un solo uso y 30 s de vida para abrir el WebSocket (en vez del JWT en la URL)."""
    ticket = secrets.token_urlsafe(32)
    cache.set(f"ws-ticket:{ticket}", usuario.pk, timeout=DURACION_TICKET)
    return ticket


async def _consumir_ticket(ticket: str) -> int | None:
    clave = f"ws-ticket:{ticket}"
    usuario_id = await cache.aget(clave)
    if usuario_id is not None and await cache.adelete(clave):  # adelete devuelve False si otro lo consumió antes
        return usuario_id
    return None


@database_sync_to_async
def _usuario(usuario_id: int):
    return get_user_model().objects.filter(pk=usuario_id, is_active=True).first() or AnonymousUser()


class TicketAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        ticket = parse_qs(scope["query_string"].decode()).get("ticket", [""])[0]
        usuario_id = await _consumir_ticket(ticket) if ticket else None
        scope["user"] = await _usuario(usuario_id) if usuario_id else AnonymousUser()
        return await super().__call__(scope, receive, send)
