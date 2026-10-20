import logging

from celery import Task, shared_task

from core.circuito import CircuitoAbierto

from . import services
from .ia import ErrorRespuestaIA, ErrorTransitorioIA
from .models import Ticket

logger = logging.getLogger(__name__)


class TareaTicket(Task):
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Fallo definitivo (sin más reintentos o error no previsto): el ticket queda en `error`."""
        logger.warning("Ticket %s fallido: %r", args[0], exc)
        services.marcar_error(args[0], f"{exc.__class__.__name__}: {exc}")


@shared_task(
    base=TareaTicket,
    bind=True,
    acks_late=True,  # si el worker muere a mitad, RabbitMQ entrega el mensaje a otro (por eso es idempotente)
    autoretry_for=(ErrorTransitorioIA, CircuitoAbierto),
    retry_backoff=30,  # 30 s, 60 s, 120 s… (con jitter) hasta retry_backoff_max
    retry_backoff_max=900,
    retry_jitter=True,
    max_retries=5,
    rate_limit="30/m",  # por worker: no saturar la cuota del proveedor de IA
)
def procesar_ticket(self, ticket_id: int) -> str:
    ticket = services.empezar(ticket_id)
    if ticket is None:
        return "omitido"
    try:
        ticket = services.procesar(ticket)
    except ErrorRespuestaIA as e:
        # la IA ha respondido algo inservible: reintentar no lo arreglará → el usuario lo completa a mano
        services.marcar_error(ticket_id, str(e), estado=Ticket.Estado.REVISAR)
        return Ticket.Estado.REVISAR
    return ticket.estado
