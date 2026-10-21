# infra/ci/dobles.Dockerfile — los servicios EXTERNOS de producción, de mentira, para el CI (módulo 83, ejercicio 4)
# SMTP (aiosmtpd, en vez de Brevo) e IA (un servidor de 20 líneas, en vez de Gemini). El S3 es RustFS.
FROM python:3.13-slim
RUN pip install --no-cache-dir "aiosmtpd==1.*"
COPY ia_falsa.py /ia_falsa.py
