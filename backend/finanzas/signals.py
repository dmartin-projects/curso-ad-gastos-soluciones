from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_delete
from django.dispatch import Signal, receiver

from core.agrupar import agrupar
from hogares.signals import hogar_creado

from . import dashboard
from .models import Categoria, Movimiento, Presupuesto
from .servicios_categorias import crear_categorias_por_defecto

# Cambios en bloque que NO emiten post_save (bulk_create, update, delete de QuerySet).
# Argumentos: hogar_id, meses (set de date, día 1). Lo escuchan el dashboard (77) y las alertas (76).
movimientos_cambiados = Signal()

# Exportación a Excel terminada. Argumentos: hogar, usuario_id, archivo (identificador para descargarla).
exportacion_lista = Signal()


@receiver(hogar_creado, dispatch_uid="finanzas_categorias_por_defecto")
def al_crear_hogar(sender, hogar, **kwargs):
    crear_categorias_por_defecto(hogar)


@receiver([post_save, post_delete], sender=Movimiento, dispatch_uid="finanzas_movimiento_cambiado")
def al_cambiar_movimiento(sender, instance, **kwargs):
    """Cambios de uno en uno (API, backoffice, tickets) → la misma señal que los cambios en bloque."""
    hogar_id, meses = instance.hogar_id, instance.meses_afectados()
    instance._fecha_cargada = instance.fecha  # el siguiente save() de esta misma instancia parte de aquí
    transaction.on_commit(lambda: movimientos_cambiados.send(sender=Movimiento, hogar_id=hogar_id, meses=meses))


@receiver([post_save, post_delete], sender=Presupuesto, dispatch_uid="finanzas_presupuesto_cambiado")
def al_cambiar_presupuesto(sender, instance, **kwargs):
    hogar_id, meses = instance.hogar_id, {instance.mes}
    transaction.on_commit(lambda: movimientos_cambiados.send(sender=Presupuesto, hogar_id=hogar_id, meses=meses))


# Borrar una categoría deja sus movimientos sin categoría (on_delete=SET_NULL) con un UPDATE en bloque, sin
# post_save: pre_delete apunta sus meses (después del UPDATE ya no se sabe qué movimientos eran suyos) y
# post_delete avisa. Las subcategorías, borradas en cascada, pasan también por aquí.
@receiver(pre_delete, sender=Categoria, dispatch_uid="finanzas_categoria_va_a_borrarse")
def antes_de_borrar_categoria(sender, instance, **kwargs):
    instance._meses_afectados = set(instance.movimientos.dates("fecha", "month"))


@receiver(post_delete, sender=Categoria, dispatch_uid="finanzas_categoria_borrada")
def al_borrar_categoria(sender, instance, **kwargs):
    if meses := getattr(instance, "_meses_afectados", None):
        hogar_id = instance.hogar_id
        transaction.on_commit(lambda: movimientos_cambiados.send(sender=Categoria, hogar_id=hogar_id, meses=meses))


@receiver(movimientos_cambiados, dispatch_uid="finanzas_comprobar_presupuestos")
def revisar_presupuestos(sender, hogar_id, meses, **kwargs):
    from .tasks import comprobar_presupuestos_tarea

    for mes in meses:
        agrupar(f"presupuestos:{hogar_id}:{mes:%Y-%m}", 10, comprobar_presupuestos_tarea, hogar_id, [mes.isoformat()])


@receiver(movimientos_cambiados, dispatch_uid="finanzas_invalidar_dashboard")
def invalidar_dashboard(sender, hogar_id, **kwargs):
    dashboard.invalidar(hogar_id)  # O(1): sube la versión del hogar (módulo 77)
    calentar(hogar_id)


def calentar(hogar_id: int) -> None:
    from .tasks import calentar_dashboard

    # agrupado: una importación de 500 filas o 20 ediciones seguidas → UN recálculo al final de la ventana
    agrupar(f"calentar-dashboard:{hogar_id}", 5, calentar_dashboard, hogar_id)


@receiver([post_save, post_delete], sender=Categoria, dispatch_uid="finanzas_categoria_cambiada")
def al_cambiar_categoria(sender, instance, **kwargs):
    # nombre, color o jerarquía cambian el dashboard aunque no cambie ningún movimiento
    hogar_id = instance.hogar_id
    transaction.on_commit(lambda: (dashboard.invalidar(hogar_id), calentar(hogar_id)))
