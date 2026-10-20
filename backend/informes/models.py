import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.models import ModeloConFechas
from hogares.models import Hogar


def ruta_informe(instancia: "InformeMensual", nombre: str) -> str:
    # un nombre nuevo en cada generación: la URL vieja (y la caché del navegador) no sirven el PDF anterior
    return f"informes/{instancia.hogar_id}/{instancia.mes:%Y-%m}-{uuid.uuid4().hex[:8]}.pdf"


class InformeMensual(ModeloConFechas):
    hogar = models.ForeignKey(Hogar, on_delete=models.CASCADE, related_name="informes")
    mes = models.DateField(_("mes"))
    archivo = models.FileField(upload_to=ruta_informe)
    tamano = models.PositiveIntegerField(default=0)
    generado_por = models.ForeignKey(  # null = generado automáticamente (Celery Beat)
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    class Meta:
        verbose_name = _("informe mensual")
        verbose_name_plural = _("informes mensuales")
        ordering = ["-mes"]
        constraints = [
            models.UniqueConstraint(fields=["hogar", "mes"], name="informe_unico_por_mes"),
            models.CheckConstraint(condition=Q(mes__day=1), name="informe_mes_dia_1"),
        ]

    def __str__(self):
        return f"{self.hogar} {self.mes:%Y-%m}"
