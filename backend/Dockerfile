# syntax=docker/dockerfile:1
# backend/Dockerfile — una imagen para web, workers, beat, tasks-worker y migrate (módulos 64 y 83)

############ Etapa 1: dependencias ############
FROM python:3.13-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

############ Etapa 2: imagen final ############
FROM python:3.13-slim AS runtime

# libpq (psycopg), pango/harfbuzz (WeasyPrint, módulo 78), Tesseract en español (OCR, módulo 74)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b libharfbuzz-subset0 fonts-dejavu-core \
        tesseract-ocr tesseract-ocr-spa curl \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=builder --chown=app:app /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    XDG_CACHE_HOME=/tmp/.cache \
    DJANGO_SETTINGS_MODULE=config.settings.prod

# Estáticos en el build (los de DRF y drf-spectacular; los sirve WhiteNoise). Sin traducciones que compilar:
# si añades locale/, añade aquí compilemessages (y gettext arriba).
RUN DJANGO_SETTINGS_MODULE=config.settings.build python manage.py collectstatic --noinput

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS http://localhost:8000/health/live/ || exit 1

# ASGI: API, WebSockets (Channels) y descargas en el mismo servidor. --no-control-socket: el socket de gunicornc
# (gunicorn 25.1+) iría a ~/.gunicorn, dentro de /app, donde el usuario app no escribe; y los procesos ya los gestiona
# Docker (reinicios, réplicas, límite de memoria): cambiar los workers en caliente no está previsto
CMD ["gunicorn", "config.asgi:application", \
     "--worker-class", "uvicorn_worker.UvicornWorker", \
     "--bind", "0.0.0.0:8000", "--workers", "3", \
     "--max-requests", "1000", "--max-requests-jitter", "100", \
     "--graceful-timeout", "30", "--access-logfile", "-", \
     "--no-control-socket"]
