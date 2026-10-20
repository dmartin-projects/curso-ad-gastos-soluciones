"""Traduce lo que pasa en el dominio (signals de las demás apps) en avisos para las personas.

Las demás apps no saben que existen las notificaciones: solo emiten señales (módulo 15).
"""

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils.translation import gettext_lazy as _

from core.agrupar import agrupar
from finanzas.servicios_presupuestos import presupuesto_superado
from finanzas.signals import movimientos_cambiados
from hogares.models import Membresia
from importaciones.models import Importacion
from importaciones.signals import importacion_analizada, importacion_progreso, importacion_terminada
from informes.signals import informe_generado
from tickets.models import Ticket
from tickets.signals import ticket_terminado

from .models import Notificacion
from .services import avisar_cambio_de_grupos, emitir_a_hogar, notificar

T = Notificacion.Tipo

# ── Tickets ──
TEXTOS_TICKET = {
    Ticket.Estado.PROCESADO: (
        T.TICKET_PROCESADO,
        _("Ticket de %(comercio)s procesado"),
        _("Se ha creado un gasto de %(total)s €."),
    ),
    Ticket.Estado.REVISAR: (
        T.TICKET_REVISAR,
        _("Revisa el ticket de %(comercio)s"),
        _("Hay datos que no se han podido confirmar."),
    ),
    Ticket.Estado.ERROR: (
        T.TICKET_ERROR,
        _("No se ha podido procesar un ticket"),
        _("Puedes reprocesarlo o introducir los datos a mano."),
    ),
}


@receiver(ticket_terminado, dispatch_uid="notif_ticket_terminado")
def al_terminar_ticket(sender, ticket, **kwargs):
    emitir_a_hogar(ticket.hogar_id, "tickets_cambiados", {"id": ticket.pk, "estado": ticket.estado})
    if ticket.subido_por is None or ticket.estado not in TEXTOS_TICKET:
        return
    tipo, titulo, mensaje = TEXTOS_TICKET[ticket.estado]
    notificar(
        [ticket.subido_por],
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje,
        contexto={
            "comercio": ticket.datos_ia.get("comercio") or ticket.nombre_original,
            "total": ticket.datos_ia.get("total") or "—",
        },
        hogar=ticket.hogar,
        enlace=f"/hogares/{ticket.hogar_id}/tickets/{ticket.pk}",
    )


# ── Importaciones ──
def _enlace(imp: Importacion) -> str:
    return f"/hogares/{imp.hogar_id}/importaciones/{imp.pk}"


@receiver(importacion_analizada, dispatch_uid="notif_importacion_analizada")
def al_analizar(sender, importacion, **kwargs):
    emitir_a_hogar(importacion.hogar_id, "importaciones_cambiadas", {"id": importacion.pk})
    if importacion.subido_por:
        notificar(
            [importacion.subido_por],
            tipo=T.IMPORTACION_LISTA,
            titulo=_("%(archivo)s está listo para revisar"),
            mensaje=_("%(filas)s movimientos leídos; %(duplicadas)s ya existían."),
            contexto={
                "archivo": importacion.nombre_original,
                "filas": importacion.total_filas,
                "duplicadas": importacion.duplicados,
            },
            hogar=importacion.hogar,
            enlace=_enlace(importacion),
        )


@receiver(importacion_progreso, dispatch_uid="notif_importacion_progreso")
def al_progresar(sender, importacion, **kwargs):
    # efímero: no se guarda, solo mueve la barra de progreso de quien esté mirando
    emitir_a_hogar(
        importacion.hogar_id, "importacion_progreso", {"id": importacion.pk, "progreso": importacion.progreso}
    )


@receiver(importacion_terminada, dispatch_uid="notif_importacion_terminada")
def al_terminar_importacion(sender, importacion, **kwargs):
    emitir_a_hogar(importacion.hogar_id, "importaciones_cambiadas", {"id": importacion.pk})
    if not importacion.subido_por:
        return
    if importacion.estado == Importacion.Estado.COMPLETADA:
        tipo, titulo = T.IMPORTACION_COMPLETADA, _("Importación de %(archivo)s completada")
        mensaje = _("%(creados)s movimientos nuevos y %(conciliados)s conciliados con gastos que ya tenías.")
    else:
        tipo, titulo, mensaje = T.IMPORTACION_ERROR, _("Error al importar %(archivo)s"), _("%(error)s")
    notificar(
        [importacion.subido_por],
        tipo=tipo,
        titulo=titulo,
        mensaje=mensaje,
        contexto={
            "archivo": importacion.nombre_original,
            "creados": importacion.creados,
            "conciliados": importacion.conciliados,
            "error": importacion.error,
        },
        hogar=importacion.hogar,
        enlace=_enlace(importacion),
    )


# ── Presupuestos y movimientos ──
@receiver(presupuesto_superado, dispatch_uid="notif_presupuesto_superado")
def al_superar_presupuesto(sender, presupuesto, **kwargs):
    p = presupuesto
    miembros = get_user_model().objects.filter(membresias__hogar_id=p.hogar_id, is_active=True)
    notificar(
        miembros,
        tipo=T.PRESUPUESTO_SUPERADO,
        titulo=_("Presupuesto de %(categoria)s superado"),
        mensaje=_("Lleváis %(gastado)s € de %(importe)s € en %(mes)s."),
        contexto={
            "categoria": p.categoria.nombre,
            "gastado": abs(p.gastado),
            "importe": p.importe,
            "mes": f"{p.mes:%m/%Y}",
        },
        hogar=p.hogar,
        enlace=f"/hogares/{p.hogar_id}/presupuestos?mes={p.mes:%Y-%m}",
        email=True,
    )


@receiver(movimientos_cambiados, dispatch_uid="notif_movimientos_cambiados")
def al_cambiar_movimientos(sender, hogar_id, meses, **kwargs):
    from .tasks import emitir_evento_hogar

    agrupar(f"ws-movimientos:{hogar_id}", 2, emitir_evento_hogar, hogar_id, "movimientos_cambiados")


# ── Membresías: los grupos del socket dependen de ellas ──
@receiver(post_save, sender=Membresia, dispatch_uid="notif_membresia_creada")
def al_crear_membresia(sender, instance, created, **kwargs):
    if created:
        transaction.on_commit(lambda: avisar_cambio_de_grupos(instance.usuario_id))


@receiver(post_delete, sender=Membresia, dispatch_uid="notif_membresia_borrada")
def al_borrar_membresia(sender, instance, **kwargs):
    transaction.on_commit(lambda: avisar_cambio_de_grupos(instance.usuario_id))


# ── Informes ──
@receiver(informe_generado, dispatch_uid="notif_informe_generado")
def al_generar_informe(sender, informe, **kwargs):
    notificar(
        get_user_model().objects.filter(membresias__hogar_id=informe.hogar_id, is_active=True),
        tipo=T.INFORME_LISTO,
        titulo=_("Informe de %(mes)s disponible"),
        contexto={"mes": f"{informe.mes:%m/%Y}"},
        hogar=informe.hogar,
        enlace=f"/hogares/{informe.hogar_id}/informes",
    )
