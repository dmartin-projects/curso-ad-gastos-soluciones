from datetime import date

from celery import shared_task

from .servicios_presupuestos import comprobar_presupuestos


@shared_task(acks_late=True, ignore_result=True)
def comprobar_presupuestos_tarea(hogar_id: int, meses: list[str]) -> None:
    comprobar_presupuestos(hogar_id, [date.fromisoformat(m) for m in meses])


@shared_task(acks_late=True, ignore_result=True)
def exportar_movimientos_xlsx(hogar_id: int, usuario_id: int, params: dict[str, list[str]]) -> None:
    from hogares.models import Hogar

    from .exportacion import generar_xlsx
    from .models import Movimiento
    from .signals import exportacion_lista

    hogar = Hogar.objects.get(pk=hogar_id)
    archivo = generar_xlsx(hogar, params)
    exportacion_lista.send(sender=Movimiento, hogar=hogar, usuario_id=usuario_id, archivo=archivo)
