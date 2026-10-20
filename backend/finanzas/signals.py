from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import Signal, receiver

from core.agrupar import agrupar
from hogares.signals import hogar_creado

from . import dashboard
from .models import Categoria, Movimiento, Presupuesto
from .servicios_categorias import crear_categorias_por_defecto

# Cambios en bloque que NO emiten post_save (bulk_create, update, delete de QuerySet).
# Argumentos: hogar_id, meses (set de date, día 1). Lo escuchan el dashboard (77) y las alertas (76).
movimientos_cambiados = Signal()


@receiver(hogar_creado, dispatch_uid="finanzas_categorias_por_defecto")
def al_crear_hogar(sender, hogar, **kwargs):
    crear_categorias_por_defecto(hogar)


@receiver([post_save, post_delete], sender=Movimiento, dispatch_uid="finanzas_movimiento_cambiado")
def al_cambiar_movimiento(sender, instance, **kwargs):
    """Cambios de uno en uno (API, backoffice, tickets) → la misma señal que los cambios en bloque."""
    hogar_id, meses = instance.hogar_id, {instance.fecha.replace(day=1)}
    transaction.on_commit(lambda: movimientos_cambiados.send(sender=Movimiento, hogar_id=hogar_id, meses=meses))


@receiver(post_save, sender=Presupuesto, dispatch_uid="finanzas_presupuesto_guardado")
def al_guardar_presupuesto(sender, instance, **kwargs):
    hogar_id, meses = instance.hogar_id, {instance.mes}
    transaction.on_commit(lambda: movimientos_cambiados.send(sender=Presupuesto, hogar_id=hogar_id, meses=meses))


@receiver(movimientos_cambiados, dispatch_uid="finanzas_comprobar_presupuestos")
def revisar_presupuestos(sender, hogar_id, meses, **kwargs):
    from .tasks import comprobar_presupuestos_tarea

    for mes in meses:
        agrupar(f"presupuestos:{hogar_id}:{mes:%Y-%m}", 10, comprobar_presupuestos_tarea, hogar_id, [mes.isoformat()])


@receiver(movimientos_cambiados, dispatch_uid="finanzas_invalidar_dashboard")
def invalidar_dashboard(sender, hogar_id, **kwargs):
    dashboard.invalidar(hogar_id)  # O(1): sube la versión del hogar (módulo 77)


@receiver([post_save, post_delete], sender=Categoria, dispatch_uid="finanzas_categoria_cambiada")
def al_cambiar_categoria(sender, instance, **kwargs):
    # nombre, color o jerarquía cambian el dashboard aunque no cambie ningún movimiento
    hogar_id = instance.hogar_id
    transaction.on_commit(lambda: dashboard.invalidar(hogar_id))
