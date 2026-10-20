"""SOLO para los comandos del build de la imagen (collectstatic): sin BD ni secretos reales (módulo 64)."""

import os

for variable in ("DJANGO_SECRET_KEY", "JWT_SIGNING_KEY", "IA_API_KEY", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY",
                 "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD"):  # fmt: skip
    os.environ.setdefault(variable, "solo-para-el-build")
for variable in ("DJANGO_CSRF_TRUSTED_ORIGINS", "FRONTEND_URL", "S3_ENDPOINT_URL"):
    os.environ.setdefault(variable, "https://build.invalid")
os.environ.setdefault("DJANGO_ALLOWED_HOSTS", "build.invalid")
os.environ.setdefault("DATABASE_URL", "sqlite:////tmp/build.db")

from .prod import *  # noqa: E402,F401,F403
