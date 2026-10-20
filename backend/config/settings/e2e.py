"""Backend para las pruebas de punta a punta (Playwright, módulo 82): todo en un proceso, sin servicios externos.

DJANGO_SETTINGS_MODULE=config.settings.e2e uv run python manage.py runserver 8000
"""

from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
ROOT_URLCONF = "config.urls_e2e"
DATABASES["default"]["NAME"] = env("E2E_DB_NAME", default="gastos_e2e")

STORAGES["default"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}
MEDIA_ROOT = BASE_DIR / "media-e2e"
CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}  # un solo proceso (daphne)
CELERY_TASK_ALWAYS_EAGER = True  # las tareas se ejecutan al encolarlas (en on_commit, tras responder)
CELERY_TASK_EAGER_PROPAGATES = False
# Con "eager" no hay countdown: la tarea agrupada se ejecutaría al PRINCIPIO de la ventana y los cambios
# de los 10 s siguientes se descartarían (un presupuesto creado y, justo después, el gasto que lo supera:
# el aviso no llegaría nunca). En E2E cada cambio lanza su tarea (módulo 82).
AGRUPAR_TAREAS = False
TASKS = {"default": {"BACKEND": "django.tasks.backends.immediate.ImmediateBackend", "QUEUES": ["default", "emails"]}}
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}

# La "IA" es una vista de este mismo servidor que contesta como Chat Completions (config/urls_e2e.py)
# con varios workers de Playwright (módulo 82) cada backend escucha en su puerto: E2E_PUERTO
IA_BASE_URL = f"http://localhost:{env('E2E_PUERTO', default='8000')}/e2e/ia/"
IA_API_KEY = "e2e"

# Los tests entran muchas veces por minuto: el límite real de "login" (5/min, módulo 35) los haría fallar
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {**REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "login": "1000/min"}
