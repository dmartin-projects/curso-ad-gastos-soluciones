from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.models import ModeloConFechas
from hogares.models import Hogar


class Notificacion(ModeloConFechas):
    class Tipo(models.TextChoices):
        TICKET_PROCESADO = "ticket_procesado", _("Ticket procesado")
        TICKET_REVISAR = "ticket_revisar", _("Ticket pendiente de revisión")
        TICKET_ERROR = "ticket_error", _("Error al procesar un ticket")
        IMPORTACION_LISTA = "importacion_lista", _("Importación lista para revisar")
        IMPORTACION_COMPLETADA = "importacion_completada", _("Importación completada")
        IMPORTACION_ERROR = "importacion_error", _("Error en una importación")
        PRESUPUESTO_SUPERADO = "presupuesto_superado", _("Presupuesto superado")
        PRESUPUESTO_80 = "presupuesto_80", _("Presupuesto al 80 %")
        INFORME_LISTO = "informe_listo", _("Informe mensual disponible")
        EXPORTACION_LISTA = "exportacion_lista", _("Exportación lista")

    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notificaciones")
    hogar = models.ForeignKey(Hogar, on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    tipo = models.CharField(max_length=30, choices=Tipo)
    titulo = models.CharField(max_length=150)
    mensaje = models.TextField(blank=True)
    enlace = models.CharField(max_length=200, blank=True)  # ruta del frontend: /hogares/3/tickets/7
    datos = models.JSONField(default=dict, blank=True)
    leida = models.BooleanField(default=False)
    leida_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("notificación")
        verbose_name_plural = _("notificaciones")
        ordering = ["-creado", "-id"]
        indexes = [
            models.Index(fields=["usuario", "-creado", "-id"], name="notif_usuario_creado"),
            # el contador de no leídas se consulta en cada carga de página: índice parcial, pequeño y exacto
            models.Index(fields=["usuario"], condition=Q(leida=False), name="notif_no_leidas"),
        ]

    def __str__(self):
        return self.titulo
