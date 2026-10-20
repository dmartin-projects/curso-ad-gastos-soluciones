import uuid
from pathlib import Path

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.models import ModeloConFechas
from finanzas.models import Cuenta, Movimiento
from hogares.models import Hogar


def ruta_importacion(instancia: "Importacion", nombre: str) -> str:
    return f"importaciones/{instancia.hogar_id}/{uuid.uuid4().hex}{Path(nombre).suffix.lower()}"


class Importacion(ModeloConFechas):
    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", _("Pendiente")
        ANALIZANDO = "analizando", _("Analizando")
        VISTA_PREVIA = "vista_previa", _("Vista previa")
        IMPORTANDO = "importando", _("Importando")
        COMPLETADA = "completada", _("Completada")
        ERROR = "error", _("Error")
        DESHECHA = "deshecha", _("Deshecha")

    class Formato(models.TextChoices):
        CSV = "csv", "CSV"
        PDF = "pdf", "PDF"

    hogar = models.ForeignKey(Hogar, on_delete=models.CASCADE, related_name="importaciones")
    cuenta = models.ForeignKey(Cuenta, on_delete=models.PROTECT, related_name="importaciones")
    subido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    archivo = models.FileField(upload_to=ruta_importacion)
    nombre_original = models.CharField(max_length=200)
    formato = models.CharField(max_length=3, choices=Formato)
    huella_archivo = models.CharField(max_length=64, editable=False)

    estado = models.CharField(max_length=12, choices=Estado, default=Estado.PENDIENTE)
    total_filas = models.PositiveIntegerField(default=0)
    procesadas = models.PositiveIntegerField(default=0)  # avanza lote a lote (progreso)
    creados = models.PositiveIntegerField(default=0)
    conciliados = models.PositiveIntegerField(default=0)
    duplicados = models.PositiveIntegerField(default=0)
    avisos = models.JSONField(default=list, blank=True)  # [{"linea": 7, "mensaje": "…"}]
    resumen = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    terminado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("importación")
        verbose_name_plural = _("importaciones")
        ordering = ["-creado"]
        constraints = [
            # el mismo extracto no se importa dos veces… salvo que la importación anterior se deshiciera o fallara
            models.UniqueConstraint(
                fields=["hogar", "huella_archivo"],
                condition=~Q(estado__in=["deshecha", "error"]),
                name="importacion_archivo_unico_activo",
            ),
        ]

    def __str__(self):
        return f"{self.nombre_original} ({self.get_estado_display()})"

    @property
    def progreso(self) -> int:
        if self.estado == self.Estado.COMPLETADA:
            return 100
        a_importar = self.resumen.get("a_importar", 0)
        return min(100, self.procesadas * 100 // a_importar) if a_importar else 0


class FilaImportacion(models.Model):
    """Área de preparación (*staging*): lo leído del archivo, ya normalizado, antes de crear nada."""

    class Accion(models.TextChoices):
        CREAR = "crear", _("Crear")
        DUPLICADA = "duplicada", _("Ya existe")
        CONCILIAR = "conciliar", _("Coincide con un gasto existente")

    importacion = models.ForeignKey(Importacion, on_delete=models.CASCADE, related_name="filas")
    numero = models.PositiveIntegerField()  # línea del archivo (para los mensajes)
    fecha = models.DateField()
    concepto = models.CharField(max_length=255)
    importe = models.DecimalField(max_digits=12, decimal_places=2)
    huella = models.CharField(max_length=64)
    accion = models.CharField(max_length=10, choices=Accion)
    coincide_con = models.ForeignKey(Movimiento, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    movimiento = models.ForeignKey(Movimiento, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["numero"]
        constraints = [models.UniqueConstraint(fields=["importacion", "numero"], name="fila_numero_unico")]
        indexes = [models.Index(fields=["importacion", "accion"], name="fila_importacion_accion")]

    def __str__(self):
        return f"{self.fecha} {self.concepto} {self.importe}"
