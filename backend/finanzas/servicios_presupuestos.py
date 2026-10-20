from decimal import Decimal

from django.dispatch import Signal

from .models import Presupuesto

# Argumentos: presupuesto (anotado con `gastado`). Lo escuchan las notificaciones (módulo 76).
presupuesto_superado = Signal()
# Mismos argumentos. Se emite al pasar del 80 % sin llegar al 100 % (si salta de golpe, solo "superado").
presupuesto_casi_agotado = Signal()

UMBRAL_AVISO = Decimal("0.8")


def comprobar_presupuestos(hogar_id: int, meses) -> list[Presupuesto]:
    """Detecta los presupuestos que acaban de superarse (y rearma los que han vuelto a estar por debajo).

    Una consulta para todos los presupuestos de esos meses (`con_gastado`, Subquery) y un UPDATE
    condicional por cambio: si dos tareas comprueban a la vez, solo una ve la fila "sin avisar" y avisa.
    """
    superados = []
    for p in Presupuesto.objects.filter(hogar_id=hogar_id, mes__in=meses).con_gastado().select_related("categoria"):
        superado = abs(p.gastado) >= p.importe
        casi = abs(p.gastado) >= p.importe * UMBRAL_AVISO
        if _cambiar(p, "alerta_enviada", superado) and superado:
            superados.append(p)
            presupuesto_superado.send(sender=Presupuesto, presupuesto=p)
        if _cambiar(p, "aviso_enviado", casi) and casi and not superado:
            presupuesto_casi_agotado.send(sender=Presupuesto, presupuesto=p)
    return superados


def _cambiar(p: Presupuesto, campo: str, valor: bool) -> bool:
    """UPDATE condicional: True solo para la tarea que de verdad cambia el valor (las demás ven 0 filas)."""
    if getattr(p, campo) == valor:
        return False
    return bool(Presupuesto.objects.filter(pk=p.pk, **{campo: not valor}).update(**{campo: valor}))
