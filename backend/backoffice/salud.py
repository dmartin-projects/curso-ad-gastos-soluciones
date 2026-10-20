"""Salud de Celery para el resumen del backoffice (módulo 79, ejercicio 1)."""

import logging

from django.conf import settings
from django.core.cache import cache

from config.celery import app

logger = logging.getLogger(__name__)
CLAVE, DURACION = "backoffice:salud-colas", 30


def _pendientes(conexion, nombres: list[str]) -> dict[str, int | None]:
    """Mensajes esperando en cada cola, preguntando al broker (no a los workers)."""
    resultado = {}
    for nombre in nombres:
        # Un canal por cola: en AMQP, declarar en pasivo una cola que no existe CIERRA el canal
        try:
            with conexion.channel() as canal:
                resultado[nombre] = canal.queue_declare(queue=nombre, passive=True).message_count
        except Exception:  # cola aún no creada…  # noqa: BLE001
            resultado[nombre] = None
    return resultado


def calcular(timeout: float = 1.0) -> dict:
    try:
        conexion = app.connection_for_write()
        # Sin reintentos: si el broker está caído, el resumen lo dice en 1 s en vez de colgarse reintentando
        conexion.ensure_connection(max_retries=1, timeout=timeout)
    except Exception as e:  # el resumen no se puede caer porque el broker lo esté  # noqa: BLE001
        logger.warning("No se pudo contactar con el broker: %r", e)
        return {"workers": 0, "colas": [], "error": "No se puede contactar con el broker."}
    try:
        # inspect() difunde la pregunta y espera `timeout` segundos a que respondan los workers vivos
        activas = app.control.inspect(timeout=timeout, connection=conexion).active_queues() or {}
        por_cola: dict[str, int] = {}
        for colas in activas.values():
            for cola in colas:
                por_cola[cola["name"]] = por_cola.get(cola["name"], 0) + 1
        nombres = sorted(set(por_cola) | {settings.CELERY_TASK_DEFAULT_QUEUE, "ocr"})
        pendientes = _pendientes(conexion, nombres)
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo consultar Celery: %r", e)
        return {"workers": 0, "colas": [], "error": "No se pudo consultar Celery."}
    finally:
        conexion.release()
    return {
        "workers": len(activas),
        "colas": [{"nombre": n, "workers": por_cola.get(n, 0), "pendientes": pendientes[n]} for n in nombres],
        "error": "",
    }


def salud_colas() -> dict:
    """Cacheado 30 s: con varios del equipo mirando el panel, el broker recibe una pregunta cada 30 s, no una por visita."""
    return cache.get_or_set(CLAVE, calcular, DURACION)
