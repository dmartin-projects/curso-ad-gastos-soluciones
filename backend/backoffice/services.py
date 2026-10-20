from django.db import transaction
from django.db.models.functions import TruncMonth
from django.forms.models import model_to_dict
from rest_framework.exceptions import ValidationError

from core.auditoria import registrar
from core.models import RegistroAuditoria
from finanzas.models import Comercio, Movimiento
from finanzas.signals import movimientos_cambiados

A = RegistroAuditoria.Accion


@transaction.atomic
def fusionar_comercios(origen: list[int], destino: int, usuario) -> dict:
    """Los movimientos de `origen` pasan a `destino` y los duplicados se borran. Todo o nada, y auditado."""
    ids = sorted(set(origen) | {destino})
    # FOR UPDATE en orden de id: dos fusiones a la vez no se bloquean mutuamente (deadlock)
    comercios = {c.pk: c for c in Comercio.objects.select_for_update().filter(pk__in=ids).order_by("pk")}
    if faltan := set(ids) - comercios.keys():
        raise ValidationError({"origen": [f"No existen: {sorted(faltan)}"]})
    final, duplicados = comercios[destino], [comercios[i] for i in sorted(set(origen))]

    movimientos = Movimiento.objects.filter(comercio__in=duplicados)
    afectados = set(movimientos.annotate(mes=TruncMonth("fecha")).values_list("hogar_id", "mes").distinct())
    reasignados = movimientos.update(comercio=final)

    # lo que el destino no tenga y algún duplicado sí, se conserva
    antes = model_to_dict(final, fields=["nif", "categoria_sugerida"])
    final.nif = final.nif or next((c.nif for c in duplicados if c.nif), "")
    final.categoria_sugerida = final.categoria_sugerida or next(
        (c.categoria_sugerida for c in duplicados if c.categoria_sugerida), ""
    )
    final.save(update_fields=["nif", "categoria_sugerida", "actualizado"])
    registrar(final, A.MODIFICAR, usuario, antes=antes)
    for c in duplicados:
        registrar(c, A.BORRAR, usuario)  # la auditoría guarda su nombre (representacion)
    Comercio.objects.filter(pk__in=[c.pk for c in duplicados]).delete()

    # update() no emite post_save: dashboards (top comercios) de cada hogar y mes afectados
    por_hogar: dict[int, set] = {}
    for hogar_id, mes in afectados:
        por_hogar.setdefault(hogar_id, set()).add(mes)
    transaction.on_commit(
        lambda: [
            movimientos_cambiados.send(sender=Movimiento, hogar_id=h, meses=meses) for h, meses in por_hogar.items()
        ]
    )
    return {"reasignados": reasignados, "borrados": len(duplicados)}
