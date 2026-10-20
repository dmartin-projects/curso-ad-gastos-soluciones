import pytest
from asgiref.sync import sync_to_async
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

from config.asgi import application
from conftest import HogarFactory, MembresiaFactory, UsuarioFactory
from notificaciones import grupos
from notificaciones.middleware import crear_ticket

pytestmark = [pytest.mark.asyncio, pytest.mark.django_db(transaction=True)]
ORIGEN = [(b"origin", b"http://testserver")]


async def conectar(usuario=None, ticket=None):
    if usuario is not None:
        ticket = await sync_to_async(crear_ticket)(usuario)
    ws = WebsocketCommunicator(application, f"/ws/notificaciones/?ticket={ticket or ''}", headers=ORIGEN)
    conectado, codigo = await ws.connect()
    return ws, conectado, codigo


async def test_sin_ticket_o_con_ticket_usado_se_rechaza():
    usuario = await sync_to_async(UsuarioFactory)()
    ticket = await sync_to_async(crear_ticket)(usuario)

    ws, _, _ = await conectar(ticket="inventado")
    assert await ws.receive_output() == {"type": "websocket.close", "code": 4401}

    ws, conectado, _ = await conectar(ticket=ticket)
    assert conectado
    assert await ws.receive_json_from() == {"tipo": "conectado", "no_leidas": 0}
    await ws.disconnect()

    ws, _, _ = await conectar(ticket=ticket)  # un solo uso
    assert await ws.receive_output() == {"type": "websocket.close", "code": 4401}


async def test_origen_no_permitido_se_rechaza():
    usuario = await sync_to_async(UsuarioFactory)()
    ticket = await sync_to_async(crear_ticket)(usuario)
    ws = WebsocketCommunicator(
        application, f"/ws/notificaciones/?ticket={ticket}", headers=[(b"origin", b"https://malo.example")]
    )
    conectado, _ = await ws.connect()
    assert not conectado


async def test_recibe_lo_suyo_y_lo_de_sus_hogares_pero_no_lo_ajeno():
    m = await sync_to_async(MembresiaFactory)()
    otro_hogar = await sync_to_async(HogarFactory)()
    ws, conectado, _ = await conectar(m.usuario)
    assert conectado
    await ws.receive_json_from()  # conectado
    capa = get_channel_layer()

    await capa.group_send(
        grupos.de_hogar(otro_hogar.pk), {"type": "hogar.evento", "evento": "x", "hogar": 0, "datos": {}}
    )
    await capa.group_send(
        grupos.de_hogar(m.hogar_id),
        {"type": "hogar.evento", "evento": "movimientos_cambiados", "hogar": m.hogar_id, "datos": {}},
    )
    await capa.group_send(grupos.de_usuario(m.usuario_id), {"type": "notificacion.nueva", "datos": {"id": 1}})

    assert await ws.receive_json_from() == {
        "tipo": "evento",
        "evento": "movimientos_cambiados",
        "hogar": m.hogar_id,
        "datos": {},
    }
    assert await ws.receive_json_from() == {"tipo": "notificacion", "datos": {"id": 1}}
    assert await ws.receive_nothing()  # el evento del otro hogar nunca llegó
    await ws.disconnect()


async def test_si_le_quitan_de_un_hogar_se_cierra_para_reconectar():
    m = await sync_to_async(MembresiaFactory)()
    ws, _, _ = await conectar(m.usuario)
    await ws.receive_json_from()

    await sync_to_async(m.delete)()  # post_delete → on_commit (autocommit: inmediato) → grupos.cambiados

    salida = await ws.receive_output()
    assert salida == {"type": "websocket.close", "code": 4000}
