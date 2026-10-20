# usuarios/models.py
from django.conf import settings
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone

from .managers import UsuarioManager


class Usuario(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField("email", unique=True)
    nombre = models.CharField(max_length=150, blank=True)
    apellidos = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    fecha_alta = models.DateTimeField(default=timezone.now)
    idioma = models.CharField(max_length=10, choices=settings.LANGUAGES, default="es")
    zona_horaria = models.CharField(max_length=50, default="Europe/Madrid")
    # Tipos de notificación que NO quiere recibir por email (lista negra: un tipo nuevo llega por defecto).
    # Los valores son Notificacion.Tipo; se validan en la API de notificaciones, no aquí, para que
    # `usuarios` no dependa de `notificaciones`.
    emails_desactivados = ArrayField(models.CharField(max_length=30), default=list, blank=True)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"  # campo con el que se identifica
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = ["nombre"]  # los pide createsuperuser (además de email y password)

    class Meta:
        verbose_name = "usuario"

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f"{self.nombre} {self.apellidos}".strip()

    def get_short_name(self):
        return self.nombre
