from django.dispatch import Signal

from .models import Presupuesto

# Argumentos: presupuesto (anotado con `gastado`). Lo escuchan las notificaciones (módulo 76).
presupuesto_superado = Signal()


def comprobar_presupuestos(hogar_id: int, meses) -> list[Presupuesto]:
    """Detecta los presupuestos que acaban de superarse (y rearma los que han vuelto a estar por debajo).

    Una consulta para todos los presupuestos de esos meses (`con_gastado`, Subquery) y un UPDATE
    condicional por cambio: si dos tareas comprueban a la vez, solo una ve la fila "sin avisar" y avisa.
    """
    superados = []
    for p in Presupuesto.objects.filter(hogar_id=hogar_id, mes__in=meses).con_gastado().select_related("categoria"):
        superado = abs(p.gastado) >= p.importe
        if superado == p.alerta_enviada:
            continue
        cambiado = Presupuesto.objects.filter(pk=p.pk, alerta_enviada=not superado).update(alerta_enviada=superado)
        if cambiado and superado:
            superados.append(p)
            presupuesto_superado.send(sender=Presupuesto, presupuesto=p)
    return superados
