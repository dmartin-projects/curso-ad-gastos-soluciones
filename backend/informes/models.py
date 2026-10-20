import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.models import ModeloConFechas
from hogares.models import Hogar


def ruta_informe(instancia: "InformeMensual", nombre: str) -> str:
    # un nombre nuevo en cada generación: la URL vieja (y la caché del navegador) no sirven el PDF anterior
    return f"informes/{instancia.hogar_id}/{instancia.periodo}-{uuid.uuid4().hex[:8]}.pdf"


class InformeMensual(ModeloConFechas):
    """Informe en PDF de un mes o (ejercicio del módulo 78) de un año: `mes` es entonces el 1 de enero."""

    class Tipo(models.TextChoices):
        MENSUAL = "mensual", _("Mensual")
        ANUAL = "anual", _("Anual")

    hogar = models.ForeignKey(Hogar, on_delete=models.CASCADE, related_name="informes")
    tipo = models.CharField(max_length=7, choices=Tipo, default=Tipo.MENSUAL)
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
            models.UniqueConstraint(fields=["hogar", "tipo", "mes"], name="informe_unico_por_periodo"),
            models.CheckConstraint(condition=Q(mes__day=1), name="informe_mes_dia_1"),
            models.CheckConstraint(condition=Q(tipo="mensual") | Q(mes__month=1), name="informe_anual_en_enero"),
        ]

    def __str__(self):
        return f"{self.hogar} {self.periodo}"

    @property
    def es_anual(self) -> bool:
        return self.tipo == self.Tipo.ANUAL

    @property
    def periodo(self) -> str:
        """2026-10 (mensual) o 2026 (anual): en la URL, en el nombre del archivo y en el adjunto."""
        return f"{self.mes:%Y}" if self.es_anual else f"{self.mes:%Y-%m}"
