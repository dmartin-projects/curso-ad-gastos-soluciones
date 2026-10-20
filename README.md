# Gastos — proyecto final con los ejercicios resueltos

El proyecto de referencia (`gastos-referencia.zip`) **más las soluciones de todos los ejercicios de la Parte 5** (módulos 71-83), un commit por módulo: `git log --oneline` para verlos y `git show <commit>` para ver qué cambia cada solución. Inténtalos antes de mirar.

Estado comprobado: 275 tests de *backend* (cobertura 94 %), 32 de *frontend* (Vitest), 16 de punta a punta (Playwright, también con `E2E_WORKERS=2`) y el recorrido contra producción (`playwright.produccion.config.ts`, módulo 83), todos en verde.

## Estructura

```
backend/            Django 6.1 + DRF + Celery + Channels (módulos 71-79)
frontend/           Angular 22 (módulos 80-81), Playwright en e2e/ (módulo 82)
infra/              Caddyfile, proxy.Dockerfile, desplegar.sh, backup.sh (módulo 83)
compose.yaml        infraestructura de desarrollo: PostgreSQL, Redis, RabbitMQ, MinIO, Mailpit
compose.prod.yaml   producción (módulo 83)
.github/workflows/  ci.yml (con el job E2E) y release.yml
```

## Plan por fases (módulo 70)

| Fase | Módulo | Resultado |
|---|---|---|
| 1. Base | 71 | Proyecto, usuario, hogares y roles, infraestructura de desarrollo |
| 2. Dominio | 72 | Modelos, migraciones, datos por defecto, *seed* |
| 3. API | 73 | CRUD con permisos por hogar, filtros, paginación, exportación |
| 4. Tickets | 74 | Subida → OCR → IA → gasto, con revisión |
| 5. Extractos | 75 | Importación idempotente |
| 6. Tiempo real | 76 | Notificaciones y alertas de presupuesto |
| 7. Dashboard | 77 | Agregaciones y caché |
| 8. Informes | 78 | PDF mensual, email, tareas programadas |
| 9. *Backoffice* | 79 | API de soporte dentro de la app (sin Django admin) |
| 10. *Frontend* | 80, 81 | App Angular completa |
| 11. Calidad | 82 | Tests de todo el *stack* |
| 12. Producción | 83 | Despliegue gratuito con CI/CD (`docs/runbook.md` para operarlo) |

## Arrancar en local

Requisitos (módulo 00): Docker Desktop, `uv`, Node 24, y para el OCR y los PDF `brew install tesseract tesseract-lang pango`.

```bash
# 1. Infraestructura
docker compose up -d
# MinIO: entra en http://localhost:9001 (minio / minio12345) y crea el bucket "gastos"

# 2. Backend
cd backend
cp .env.example .env              # pon tu IA_API_KEY de Gemini si quieres leer tickets con IA
uv sync
uv run python manage.py migrate
uv run python manage.py seed      # demo@example.com / demo12345-demo, con datos de ejemplo
uv run python manage.py runserver # API en http://localhost:8000/api/docs/

# 3. Procesos en segundo plano (cada uno en su terminal, desde backend/)
uv run celery -A config worker -l info -Q default,ocr
uv run celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
uv run python manage.py db_worker --queue-name "*"

# 4. Frontend
cd ../frontend
npm ci
npx ng serve                      # http://localhost:4200 (el proxy envía /api y /ws a Django)
```

Personal de soporte (el *backoffice* está dentro de la app, no hay Django admin): regístrate o usa el usuario demo y ejecuta `uv run python manage.py personal demo@example.com`.

## Tests

```bash
cd backend && uv run pytest -n 4 --cov                 # 273 tests
cd frontend && npx ng test --watch=false                # 32 tests
# punta a punta (módulo 82): una vez, crea la BD de E2E
docker compose exec db createdb -U gastos gastos_e2e
cd backend && DJANGO_SETTINGS_MODULE=config.settings.e2e uv run python manage.py migrate
cd ../frontend && npx playwright install chromium && npx playwright test
```
