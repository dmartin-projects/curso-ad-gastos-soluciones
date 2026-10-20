import logging

from celery import Task, chord, shared_task
from django.conf import settings
from django.db import IntegrityError, OperationalError

from . import services

logger = logging.getLogger(__name__)


class TareaImportacion(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.warning("Importación %s fallida en %s: %r", args[0], self.name, exc)
        services.fallar(args[0], "Error inesperado al procesar el archivo.")


@shared_task(base=TareaImportacion, acks_late=True)
def analizar_importacion(importacion_id: int) -> None:
    services.analizar(importacion_id)


@shared_task(
    base=TareaImportacion,
    acks_late=True,
    # IntegrityError: un extracto solapado creó la misma huella a la vez → el reintento la verá como duplicada
    autoretry_for=(IntegrityError, OperationalError),
    retry_backoff=5,
    max_retries=3,
)
def importar_lote(importacion_id: int, ids: list[int]) -> dict:
    return services.importar_lote(importacion_id, ids)


@shared_task(acks_late=True)
def finalizar_importacion(importacion_id: int) -> None:
    services.finalizar(importacion_id)


@shared_task
def importacion_fallida(importacion_id: int) -> None:
    services.fallar(importacion_id, "No se pudieron importar todos los movimientos. Puedes deshacer y repetir.")


def lanzar_importacion(importacion_id: int, ids: list[int]) -> None:
    """Chord (módulo 26): los lotes en paralelo en todos los workers y, cuando terminan TODOS, el cierre."""
    tam = settings.IMPORTACION_TAMANO_LOTE
    lotes = [ids[i : i + tam] for i in range(0, len(ids), tam)]
    if not lotes:
        finalizar_importacion.delay(importacion_id)
        return
    cierre = finalizar_importacion.si(importacion_id).on_error(importacion_fallida.si(importacion_id))
    chord(importar_lote.si(importacion_id, lote) for lote in lotes)(cierre)
