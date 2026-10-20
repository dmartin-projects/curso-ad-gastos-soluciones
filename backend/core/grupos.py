"""Grupos de personal con sus permisos, definidos en código (versionados y repetibles en cada entorno)."""

from django.apps import apps
from django.contrib.auth.management import create_permissions
from django.contrib.auth.models import Group, Permission
from django.db.models import Q

GRUPOS = {
    "Soporte": {
        "tickets.ticket": ["view", "change"],
        "importaciones.importacion": ["view", "change"],
        "finanzas.movimiento": ["view", "change"],
        "finanzas.categoria": ["view"],
        "finanzas.comercio": ["view", "change", "delete"],  # fusionar duplicados borra (módulo 79)
        "hogares.hogar": ["view"],
        "hogares.membresia": ["view"],
        "usuarios.usuario": ["view"],
        "core.registroauditoria": ["view"],
        "django_celery_beat.periodictask": ["view"],
    },
    # Módulo 79: lo que antes exigía un superusuario. Sin tickets ni movimientos: no es soporte.
    "Administración": {
        "usuarios.usuario": ["view", "change"],
        "django_celery_beat.periodictask": ["view", "change"],
        "core.registroauditoria": ["view"],
    },
}


def crear_grupos(sender=None, **kwargs):
    """Receptor de post_migrate: deja los grupos exactamente como dice GRUPOS (idempotente)."""
    # post_migrate se emite app por app y los permisos de cada app se crean en SU señal: cuando llega la de
    # "core" (de las primeras en INSTALLED_APPS), los de tickets o finanzas aún no existen en una BD nueva.
    for app_config in apps.get_app_configs():
        create_permissions(app_config, verbosity=0)
    for nombre, por_modelo in GRUPOS.items():
        filtro = Q(pk__in=[])
        for etiqueta, acciones in por_modelo.items():
            app_label, modelo = etiqueta.split(".")
            codigos = [f"{accion}_{modelo}" for accion in acciones]
            filtro |= Q(content_type__app_label=app_label, codename__in=codigos)
        grupo, _ = Group.objects.get_or_create(name=nombre)
        grupo.permissions.set(Permission.objects.filter(filtro))
