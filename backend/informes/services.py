from datetime import date

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone, translation
from weasyprint import HTML

from finanzas import dashboard
from finanzas.models import Movimiento
from hogares.models import Hogar

from .models import InformeMensual
from .signals import informe_generado


def contexto(hogar: Hogar, mes: date) -> dict:
    return {
        "hogar": hogar,
        "resumen": dashboard.calcular(hogar, mes),  # los mismos números que el dashboard (módulo 77)
        "movimientos": (
            Movimiento.objects.del_hogar(hogar)
            .del_mes(mes)
            .con_detalle()
            # {% regroup %} agrupa elementos CONSECUTIVOS: la lista debe venir ordenada por el grupo
            .order_by("categoria__nombre", "categoria_id", "fecha", "id")
        ),
        "generado": timezone.localtime(),
    }


def pdf(hogar: Hogar, mes: date, idioma: str | None = None) -> bytes:
    with translation.override(idioma or settings.LANGUAGE_CODE):
        html = render_to_string("informes/mensual.html", contexto(hogar, mes))
    return HTML(string=html).write_pdf()


def generar(hogar_id: int, mes: date, *, usuario=None, enviar: bool = True) -> InformeMensual:
    """Genera (o regenera) el PDF del mes. Idempotente: un informe por hogar y mes (restricción única)."""
    hogar = Hogar.objects.get(pk=hogar_id)
    contenido = pdf(hogar, mes)  # fuera de la transacción: puede tardar segundos
    with transaction.atomic():
        informe = InformeMensual.objects.select_for_update().filter(hogar=hogar, mes=mes).first()
        anterior = informe.archivo.name if informe else None
        if informe is None:
            informe = InformeMensual(hogar=hogar, mes=mes)
        informe.generado_por = usuario
        informe.tamano = len(contenido)
        informe.archivo.save("informe.pdf", ContentFile(contenido), save=False)
        informe.save()
        if anterior:
            storage = informe.archivo.storage
            transaction.on_commit(lambda: storage.delete(anterior))
        transaction.on_commit(lambda: informe_generado.send(sender=InformeMensual, informe=informe, enviar=enviar))
        if enviar:
            transaction.on_commit(lambda: enviar_a_miembros(informe))
    return informe


def enviar_a_miembros(informe: InformeMensual) -> None:
    from .tasks import enviar_informe

    for usuario_id in informe.hogar.membresias.filter(usuario__is_active=True).values_list("usuario_id", flat=True):
        enviar_informe.enqueue(informe.pk, usuario_id)
