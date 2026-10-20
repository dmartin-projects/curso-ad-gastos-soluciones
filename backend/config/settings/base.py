"""Ajustes comunes a todos los entornos."""

from datetime import timedelta
from pathlib import Path

import environ
from celery.schedules import crontab
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
# Rotar la clave sin invalidar al instante sesiones, enlaces de recuperación… (módulos 29 y 67, runbook)
SECRET_KEY_FALLBACKS = env.list("DJANGO_SECRET_KEY_FALLBACKS", default=[])
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=[])

DJANGO_APPS = [
    "daphne",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
]
TERCEROS = [
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "drf_spectacular",
    "channels",
    "django_celery_beat",
    "django_tasks_db",
]
PROPIAS = [
    "core",
    "usuarios",
    "hogares",
    "finanzas",
    "tickets",
    "importaciones",
    "notificaciones",
    "informes",
    "backoffice",
]
INSTALLED_APPS = DJANGO_APPS + TERCEROS + PROPIAS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "core.logging.request_id_middleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {"default": env.db("DATABASE_URL")}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

AUTH_USER_MODEL = "usuarios.Usuario"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es"
LANGUAGES = [("es", _("Español")), ("en", _("Inglés"))]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Europe/Madrid"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default='"Gastos" <no-responder@gastos.example>')
MAILERS = {"default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}}
FRONTEND_URL = env("FRONTEND_URL", default="http://localhost:4200")

# ── Caché, Channels, Celery ──
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL", default="redis://localhost:6379/1"),
        "KEY_PREFIX": "gastos",
    }
}
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        # socket_timeout > 5: redis-py 8 lee con 5 s por defecto, lo mismo que espera el BZPOPMIN de channels_redis,
        # y un WebSocket sin mensajes se caía cada 5 s con "Timeout reading from…" (módulo 83)
        "CONFIG": {
            "hosts": [{"address": env("REDIS_CHANNELS_URL", default="redis://localhost:6379/2"), "socket_timeout": 10}]
        },
    }
}
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="amqp://guest:guest@localhost:5672//")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="redis://localhost:6379/0")
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SERIALIZER = CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_TIME_LIMIT = 300
CELERY_TASK_SOFT_TIME_LIMIT = 270
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {"tickets.tasks.*": {"queue": "ocr"}}  # el resto (importaciones…) va a "default"
# Tareas periódicas (módulo 78). Con el DatabaseScheduler de django-celery-beat se copian a la BD al
# arrancar Beat y se pueden pausar desde el backoffice (módulo 79). Horas en CELERY_TIMEZONE (Europe/Madrid).
CELERY_BEAT_SCHEDULE = {
    "informes-mensuales": {  # cada hora: la tarea decide en qué zonas horarias son ya las 7:00 del día 1
        "task": "informes.tasks.generar_informes_mensuales",
        "schedule": crontab(minute=0),
    },
    "informes-anuales": {
        "task": "informes.tasks.generar_informes_anuales",
        "schedule": crontab(minute=0, hour=7, day_of_month=2, month_of_year=1),
    },
    "caducar-vistas-previas": {
        "task": "importaciones.tasks.caducar_vistas_previas",
        "schedule": crontab(minute=15, hour=4),
    },
    "limpiar-notificaciones-leidas": {
        "task": "notificaciones.tasks.limpiar_notificaciones_leidas",
        "schedule": crontab(minute=45, hour=3, day_of_week=0),  # domingos
    },
    "limpiar-resultados-de-tareas": {
        "task": "core.tasks.limpiar_resultados_de_tareas",
        "schedule": crontab(minute=30, hour=3),
    },
}

TASKS = {"default": {"BACKEND": "django_tasks_db.DatabaseBackend", "QUEUES": ["default", "emails"]}}

# ── DRF ──
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser", "rest_framework.parsers.MultiPartParser"],
    "DEFAULT_VERSIONING_CLASS": "rest_framework.versioning.URLPathVersioning",
    "DEFAULT_VERSION": "v1",
    "ALLOWED_VERSIONS": ["v1"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.api.paginacion.PaginacionEstandar",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {
        "login": "5/min",
        "registro": "5/hour",
        "recuperar": "3/hour",
        "subidas": "60/hour",
        "baja": "30/hour",
    },
    "EXCEPTION_HANDLER": "core.api.exceptions.manejador_errores",
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
}
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "SIGNING_KEY": env("JWT_SIGNING_KEY"),
    "AUTH_HEADER_TYPES": ("Bearer",),
}
JWT_REFRESH_COOKIE = {
    "key": "refresh",
    "path": "/api/v1/auth/",
    "httponly": True,
    "secure": not DEBUG,
    "samesite": "Strict",
}
SPECTACULAR_SETTINGS = {
    "TITLE": "API Gastos",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "SCHEMA_PATH_PREFIX": r"/api/v[0-9]",
    # dos modelos con un campo "estado" de opciones distintas: nombres explícitos para sus enums
    "ENUM_NAME_OVERRIDES": {
        "EstadoTicketEnum": "tickets.models.Ticket.Estado",
        "EstadoImportacionEnum": "importaciones.models.Importacion.Estado",
        "TipoNotificacionEnum": "notificaciones.models.Notificacion.Tipo",
        "TipoInformeEnum": "informes.models.InformeMensual.Tipo",
    },
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"request_id": {"()": "core.logging.RequestIdFilter"}},
    "formatters": {
        "texto": {"format": "{asctime} {levelname} {name} [{request_id}] {message}", "style": "{"},
        "json": {
            "()": "pythonjsonlogger.json.JsonFormatter",
            "fmt": "%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s",
        },
    },
    "handlers": {
        "consola": {
            "class": "logging.StreamHandler",
            "formatter": env("LOG_FORMAT", default="texto"),
            "filters": ["request_id"],
        }
    },
    "root": {"handlers": ["consola"], "level": "INFO"},
    "loggers": {
        "django.db.backends": {"level": "WARNING"},
        "httpx": {"level": "WARNING"},
        "weasyprint": {"level": "WARNING"},  # registra cada paso de cada PDF en INFO
        "fontTools": {"level": "WARNING"},
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Tickets: OCR + IA (módulo 74) ──
# Cualquier API compatible con Chat Completions de OpenAI. Por defecto, Gemini; en local, Ollama:
# IA_BASE_URL=http://localhost:11434/v1/  IA_MODELO=<un modelo multimodal descargado>  IA_API_KEY=ollama
IA_BASE_URL = env("IA_BASE_URL", default="https://generativelanguage.googleapis.com/v1beta/openai/")
IA_API_KEY = env("IA_API_KEY", default="")
IA_MODELO = env("IA_MODELO", default="gemini-3.8-flash")
IA_TIMEOUT = env.float("IA_TIMEOUT", default=30.0)
TICKETS_UMBRAL_CONFIANZA = env.float("TICKETS_UMBRAL_CONFIANZA", default=0.8)
TICKETS_TAMANO_MAXIMO = 10 * 1024 * 1024  # 10 MB

# ── Importación de extractos (módulo 75) ──
IMPORTACION_TAMANO_MAXIMO = 5 * 1024 * 1024  # 5 MB
IMPORTACION_TAMANO_LOTE = 500  # filas por tarea del chord
IMPORTACION_DIAS_CONCILIACION = 3  # un gasto manual o de ticket y la fila del banco pueden diferir unos días
IMPORTACION_DIAS_VISTA_PREVIA = 7  # una vista previa sin confirmar se borra pasado este tiempo
