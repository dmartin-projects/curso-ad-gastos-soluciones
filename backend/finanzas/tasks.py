from datetime import date

from celery import shared_task

from .servicios_presupuestos import comprobar_presupuestos


@shared_task(acks_late=True, ignore_result=True)
def comprobar_presupuestos_tarea(hogar_id: int, meses: list[str]) -> None:
    comprobar_presupuestos(hogar_id, [date.fromisoformat(m) for m in meses])
