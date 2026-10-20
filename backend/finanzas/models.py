from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from core.models import ModeloConFechas
from hogares.models import Hogar

from .normalizacion import normalizar
from .querysets import MovimientoQuerySet, PresupuestoQuerySet


class Cuenta(ModeloConFechas):
    class Tipo(models.TextChoices):
        BANCO = "banco", _("Cuenta bancaria")
        TARJETA = "tarjeta", _("Tarjeta")
        EFECTIVO = "efectivo", _("Efectivo")

    hogar = models.ForeignKey(Hogar, on_delete=models.CASCADE, related_name="cuentas")
    nombre = models.CharField(_("nombre"), max_length=80)
    tipo = models.CharField(_("tipo"), max_length=10, choices=Tipo, default=Tipo.BANCO)
    iban = models.CharField(_("IBAN"), max_length=34, blank=True)
    activa = models.BooleanField(default=True)

    class Meta:
        verbose_name = _("cuenta")
        constraints = [models.UniqueConstraint(fields=["hogar", "nombre"], name="cuenta_nombre_unico_por_hogar")]

    def __str__(self):
        return self.nombre


class Categoria(ModeloConFechas):
    hogar = models.ForeignKey(Hogar, on_delete=models.CASCADE, related_name="categorias")
    padre = models.ForeignKey("self", on_delete=models.CASCADE, null=True, blank=True, related_name="hijas")
    nombre = models.CharField(_("nombre"), max_length=60)
    color = models.CharField(_("color"), max_length=7, default="#607d8b")
    icono = models.CharField(_("icono"), max_length=40, blank=True)
    orden = models.PositiveSmallIntegerField(default=0)
    es_ingreso = models.BooleanField(_("es de ingresos"), default=False)

    class Meta:
        verbose_name = _("categoría")
        ordering = ["orden", "nombre"]
        constraints = [
            # nulls_distinct=False: dos categorías raíz (padre NULL) con el mismo nombre también chocan
            models.UniqueConstraint(
                fields=["hogar", "padre", "nombre"], nulls_distinct=False, name="categoria_unica_por_nivel"
            ),
            models.CheckConstraint(condition=Q(color__regex=r"^#[0-9a-fA-F]{6}$"), name="categoria_color_hex"),
        ]

    def __str__(self):
        return f"{self.padre} › {self.nombre}" if self.padre_id else self.nombre


class Comercio(ModeloConFechas):
    """Comercio global (compartido entre hogares), con nombre normalizado para reconocerlo."""

    nombre = models.CharField(_("nombre"), max_length=120)
    nombre_normalizado = models.CharField(max_length=120, unique=True, editable=False)
    nif = models.CharField(_("NIF"), max_length=15, blank=True)
    categoria_sugerida = models.CharField(_("categoría sugerida"), max_length=60, blank=True)

    class Meta:
        verbose_name = _("comercio")
        indexes = [GinIndex(fields=["nombre_normalizado"], opclasses=["gin_trgm_ops"], name="comercio_trgm")]

    def save(self, *args, **kwargs):
        self.nombre_normalizado = normalizar(self.nombre)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre


class Movimiento(ModeloConFechas):
    class Origen(models.TextChoices):
        MANUAL = "manual", _("Manual")
        TICKET = "ticket", _("Ticket")
        EXTRACTO = "extracto", _("Extracto bancario")

    hogar = models.ForeignKey(Hogar, on_delete=models.CASCADE, related_name="movimientos")
    cuenta = models.ForeignKey(Cuenta, on_delete=models.PROTECT, related_name="movimientos")
    fecha = models.DateField(_("fecha"))
    importe = models.DecimalField(_("importe"), max_digits=12, decimal_places=2)  # < 0 gasto, > 0 ingreso
    concepto = models.CharField(_("concepto"), max_length=255)
    comercio = models.ForeignKey(Comercio, on_delete=models.SET_NULL, null=True, blank=True, related_name="movimientos")
    categoria = models.ForeignKey(
        Categoria, on_delete=models.SET_NULL, null=True, blank=True, related_name="movimientos"
    )
    etiquetas = ArrayField(models.CharField(max_length=30), default=list, blank=True)
    notas = models.TextField(blank=True)
    origen = models.CharField(max_length=10, choices=Origen, default=Origen.MANUAL)
    huella = models.CharField(max_length=64, blank=True, editable=False)  # importaciones (módulo 75)
    revisado = models.BooleanField(_("revisado"), default=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    adjuntos = GenericRelation("core.Adjunto", related_query_name="movimiento")  # módulo 17

    objects = MovimientoQuerySet.as_manager()

    class Meta:
        verbose_name = _("movimiento")
        ordering = ["-fecha", "-id"]
        indexes = [
            models.Index(fields=["hogar", "-fecha", "-id"], name="mov_hogar_fecha"),  # listado + cursor
            models.Index(fields=["hogar", "categoria", "fecha"], name="mov_hogar_cat_fecha"),  # dashboard
            models.Index(fields=["hogar"], condition=Q(revisado=False), name="mov_pendientes_revision"),
            GinIndex(fields=["etiquetas"], name="mov_etiquetas"),
        ]
        constraints = [
            models.CheckConstraint(condition=~Q(importe=Decimal("0")), name="movimiento_importe_no_cero"),
            models.UniqueConstraint(
                fields=["cuenta", "huella"], condition=~Q(huella=""), name="movimiento_huella_unica"
            ),
        ]

    def __str__(self):
        return f"{self.fecha} {self.concepto} {self.importe}"

    @property
    def es_gasto(self) -> bool:
        return self.importe < 0


class Presupuesto(ModeloConFechas):
    hogar = models.ForeignKey(Hogar, on_delete=models.CASCADE, related_name="presupuestos")
    categoria = models.ForeignKey(Categoria, on_delete=models.CASCADE, related_name="presupuestos")
    mes = models.DateField(_("mes"))  # siempre día 1
    importe = models.DecimalField(_("importe"), max_digits=10, decimal_places=2)
    alerta_enviada = models.BooleanField(default=False, editable=False)

    objects = PresupuestoQuerySet.as_manager()

    class Meta:
        verbose_name = _("presupuesto")
        constraints = [
            models.UniqueConstraint(fields=["hogar", "categoria", "mes"], name="presupuesto_unico"),
            models.CheckConstraint(condition=Q(mes__day=1), name="presupuesto_mes_dia_1"),
            models.CheckConstraint(condition=Q(importe__gt=0), name="presupuesto_importe_positivo"),
        ]
