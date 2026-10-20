# infra/ci/dobles.Dockerfile — los servicios EXTERNOS de producción, de mentira, para el CI (módulo 83, ejercicio 4)
# S3 (moto, en vez de R2), SMTP (aiosmtpd, en vez de Brevo) e IA (un servidor de 20 líneas, en vez de Gemini)
FROM python:3.13-slim
RUN pip install --no-cache-dir "moto[server]==5.*" "aiosmtpd==1.*"
COPY ia_falsa.py /ia_falsa.py
