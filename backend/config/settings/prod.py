"""Producción (módulo 83): lo del módulo 67, con lo propio de este proyecto."""

from .base import *  # noqa: F403

DEBUG = False
# + localhost: el healthcheck de Docker llama a http://localhost:8000/health/live/ desde dentro del contenedor
ALLOWED_HOSTS = [*env.list("DJANGO_ALLOWED_HOSTS"), "localhost"]
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS")
FRONTEND_URL = env("FRONTEND_URL")  # enlaces de los correos: sin valor por defecto, que no salgan a localhost

# ── HTTPS detrás del proxy (módulos 29 y 65) ──
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_REDIRECT_EXEMPT = [r"^health/"]  # las sondas de Docker hablan HTTP dentro de la red interna
SESSION_COOKIE_SECURE = CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=3600)  # súbelo a 1 año cuando todo funcione
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# La lista "preload" de los navegadores es casi irreversible: solo cuando HTTPS lleve meses funcionando bien
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)
if not SECURE_HSTS_PRELOAD:
    SILENCED_SYSTEM_CHECKS = ["security.W021"]  # decisión consciente, no un aviso olvidado
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
JWT_REFRESH_COOKIE["secure"] = True  # módulo 35

# ── Base de datos: pool en la web (ASGI) ──
# Con gunicorn + UvicornWorker cada petición síncrona corre en un hilo, y con CONN_MAX_AGE cada hilo se
# queda SU conexión abierta hasta 60 s: con carga, PostgreSQL responde "too many clients" (medido en el
# módulo 83: un 20 % de errores con 8 clientes). La documentación de Django lo dice: con ASGI, nada de
# conexiones persistentes; un pool. Solo en la web (DB_POOL_MAX en compose): los workers de Celery son
# procesos de un hilo, donde CONN_MAX_AGE va bien, y un pool (con su hilo) no se lleva bien con fork().
if POOL := env.int("DB_POOL_MAX", default=0):
    DATABASES["default"]["CONN_MAX_AGE"] = 0  # obligatorio con pool
    DATABASES["default"]["CONN_HEALTH_CHECKS"] = False
    DATABASES["default"]["OPTIONS"] = {
        **DATABASES["default"].get("OPTIONS", {}),
        "pool": {"min_size": 1, "max_size": POOL, "timeout": 10},  # si se agota, espera hasta 10 s
    }

# ── Archivos: S3 compatible (Cloudflare R2 u Oracle Object Storage, módulo 68) con URLs firmadas ──
STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": env("S3_BUCKET"),
            "endpoint_url": env("S3_ENDPOINT_URL"),
            "access_key": env("S3_ACCESS_KEY"),
            "secret_key": env("S3_SECRET_KEY"),
            "region_name": env("S3_REGION", default="auto"),  # R2 usa "auto"
            "default_acl": None,
            "querystring_auth": True,  # los tickets y los extractos son privados
            "querystring_expire": 300,
            "file_overwrite": False,
        },
    },
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# ── Email (módulo 22) ──
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {
            "host": env("SMTP_HOST"),
            "port": env.int("SMTP_PORT", default=587),
            "username": env("SMTP_USER"),
            "password": env("SMTP_PASSWORD"),
            "use_tls": True,
            "timeout": 10,
        },
    },
}

# ── IA (módulo 74): sin clave no hay tickets; que falle al arrancar, no con el primer ticket ──
IA_API_KEY = env("IA_API_KEY")

# ── Logs en JSON (módulo 30) ──
LOGGING["handlers"]["consola"]["formatter"] = "json"

# ── DRF (módulos 32 y 36) ──
REST_FRAMEWORK["NUM_PROXIES"] = 1  # la IP real para el throttling llega en X-Forwarded-For (Caddy)
# El esquema y Swagger, solo para el personal (en desarrollo, abiertos)
SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"] = ["rest_framework.permissions.IsAdminUser"]

# ── Sentry (módulo 30) ──
if dsn := env("SENTRY_DSN", default=""):
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment="produccion",
        release=env("VERSION", default=None),
        traces_sample_rate=0.1,
        # sin datos personales: es el comportamiento por defecto (send_default_pii está obsoleto)
    )
