from .base import *  # noqa: F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] += ["rest_framework.renderers.BrowsableAPIRenderer"]
MAILERS = {
    "default": {
        "BACKEND": "django.core.mail.backends.smtp.EmailBackend",
        "OPTIONS": {"host": "localhost", "port": 1025},
    }
}
STORAGES["default"] = {
    "BACKEND": "storages.backends.s3.S3Storage",
    "OPTIONS": {
        "bucket_name": env("S3_BUCKET", default="gastos"),
        "endpoint_url": env("S3_ENDPOINT_URL", default="http://localhost:9000"),
        "access_key": env("S3_ACCESS_KEY", default="rustfs"),
        "secret_key": env("S3_SECRET_KEY", default="rustfs12345"),
        "region_name": "us-east-1",
        "signature_version": "s3v4",  # firma v4, como en producción (ver módulo 20)
        "querystring_auth": True,
    },
}
