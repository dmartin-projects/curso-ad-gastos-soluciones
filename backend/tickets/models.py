import uuid
from pathlib import Path

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from core.models import ModeloConFechas
from finanzas.models import Cuenta, Movimiento
from hogares.models import Hogar


def ruta_ticket(instancia: "Ticket", nombre: str) -> str:
    """Nunca se usa el nombre que manda el cliente: evita colisiones, rutas raras y filtrar datos (módulo 20)."""
    return f"tickets/{instancia.hogar_id}/{uuid.uuid4().hex}{Path(nombre).suffix.lower()}"


class Ticket(ModeloConFechas):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", _("Pendiente")
        PROCESANDO = "procesando", _("Procesando")
        REVISAR = "revisar", _("Pendiente de revisión")
        PROCESADO = "procesado", _("Procesado")
        ERROR = "error", _("Error")

    hogar = models.ForeignKey(Hogar, on_delete=models.CASCADE, related_name="tickets")
    cuenta = models.ForeignKey(Cuenta, on_delete=models.PROTECT, related_name="tickets")
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    archivo = models.FileField(_("archivo"), upload_to=ruta_ticket)
    nombre_original = models.CharField(max_length=200)
    tipo = models.CharField(max_length=40)  # image/jpeg, image/png, application/pdf
    huella_archivo = models.CharField(max_length=64, editable=False)  # sha256 del contenido

    estado = models.CharField(max_length=12, choices=Estado, default=Estado.PENDIENTE)
    intentos = models.PositiveSmallIntegerField(default=0)
    texto_ocr = models.TextField(blank=True)
    datos_ia = models.JSONField(default=dict, blank=True, encoder=DjangoJSONEncoder)  # Decimal y date → texto
    confianza = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    error = models.TextField(blank=True)
    procesado_en = models.DateTimeField(null=True, blank=True)
    tokens_entrada = models.PositiveIntegerField(default=0)  # usage.prompt_tokens (acumulado)
    tokens_salida = models.PositiveIntegerField(default=0)  # usage.completion_tokens (acumulado)
    movimiento = models.OneToOneField(
        Movimiento, on_delete=models.SET_NULL, null=True, blank=True, related_name="ticket"
    )

    class Meta:
        verbose_name = _("ticket")
        ordering = ["-creado"]
        indexes = [models.Index(fields=["hogar", "estado", "-creado"], name="ticket_hogar_estado")]
        constraints = [
            # el mismo archivo no se puede subir dos veces al mismo hogar
            models.UniqueConstraint(fields=["hogar", "huella_archivo"], name="ticket_archivo_unico_por_hogar"),
            models.CheckConstraint(
                condition=Q(confianza__isnull=True) | Q(confianza__gte=0, confianza__lte=1),
                name="ticket_confianza_0_1",
            ),
        ]

    def __str__(self):
        return f"Ticket {self.pk} ({self.get_estado_display()})"


class LineaTicket(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="lineas")
    orden = models.PositiveSmallIntegerField()
    descripcion = models.CharField(max_length=200)
    cantidad = models.DecimalField(max_digits=8, decimal_places=3, default=1)
    precio_unitario = models.DecimalField(max_digits=10, decimal_places=2)
    # GeneratedField (módulo 06): la base de datos calcula y guarda el importe; nunca se desincroniza
    importe = models.GeneratedField(
        expression=F("cantidad") * F("precio_unitario"),
        output_field=models.DecimalField(max_digits=12, decimal_places=2),
        db_persist=True,
    )

    class Meta:
        ordering = ["orden"]
        constraints = [models.UniqueConstraint(fields=["ticket", "orden"], name="linea_orden_unico")]

    def __str__(self):
        return self.descripcion
