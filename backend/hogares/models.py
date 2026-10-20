import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.models import ModeloConFechas


class Hogar(ModeloConFechas):
    nombre = models.CharField(_("nombre"), max_length=100)
    moneda = models.CharField(_("moneda"), max_length=3, default="EUR")
    zona_horaria = models.CharField(_("zona horaria"), max_length=50, default="Europe/Madrid")
    miembros = models.ManyToManyField(settings.AUTH_USER_MODEL, through="Membresia", related_name="hogares")

    class Meta:
        verbose_name = _("hogar")
        verbose_name_plural = _("hogares")

    def __str__(self):
        return self.nombre


class Membresia(ModeloConFechas):
    class Rol(models.TextChoices):
        ADMIN = "admin", _("Administrador")
        MIEMBRO = "miembro", _("Miembro")
        LECTOR = "lector", _("Solo lectura")

    hogar = models.ForeignKey(Hogar, on_delete=models.CASCADE, related_name="membresias")
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="membresias")
    rol = models.CharField(_("rol"), max_length=10, choices=Rol, default=Rol.MIEMBRO)

    class Meta:
        verbose_name = _("membresía")
        constraints = [models.UniqueConstraint(fields=["hogar", "usuario"], name="membresia_unica")]

    def __str__(self):
        return f"{self.usuario} en {self.hogar} ({self.rol})"


def _token():
    return secrets.token_urlsafe(32)


def _caducidad():
    return timezone.now() + timedelta(days=7)


class Invitacion(ModeloConFechas):
    hogar = models.ForeignKey(Hogar, on_delete=models.CASCADE, related_name="invitaciones")
    email = models.EmailField()
    rol = models.CharField(max_length=10, choices=Membresia.Rol, default=Membresia.Rol.MIEMBRO)
    token = models.CharField(max_length=64, unique=True, default=_token)
    invitado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    caduca = models.DateTimeField(default=_caducidad)
    aceptada = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _("invitación")
        verbose_name_plural = _("invitaciones")
        constraints = [
            models.UniqueConstraint(
                fields=["hogar", "email"], condition=models.Q(aceptada__isnull=True), name="invitacion_pendiente_unica"
            ),
        ]

    @property
    def vigente(self) -> bool:
        return self.aceptada is None and self.caduca > timezone.now()
