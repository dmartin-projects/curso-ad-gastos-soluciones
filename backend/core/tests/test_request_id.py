import pytest


@pytest.mark.django_db
def test_x_request_id_valido_se_respeta(client):
    rid = "0b1c2d3e-4f50-6172-8394-a5b6c7d8e9f0"  # crypto.randomUUID() de Angular / {http.request.uuid} de Caddy
    assert client.get("/health/live/", HTTP_X_REQUEST_ID=rid)["X-Request-ID"] == rid


@pytest.mark.django_db
@pytest.mark.parametrize("recibido", ["", "abc\nERROR falso", "a" * 65, "<script>"])
def test_x_request_id_invalido_se_sustituye(client, recibido):
    # log injection (módulo 30): un id con saltos de línea o demasiado largo no llega a los logs
    rid = client.get("/health/live/", HTTP_X_REQUEST_ID=recibido)["X-Request-ID"]
    assert rid != recibido and len(rid) == 32 and rid.isalnum()


def test_el_worker_de_celery_usa_nuestro_logging():
    from config.celery import app

    # Por defecto, el worker cambia los handlers del root logger por los suyos: sin request_id ni JSON
    assert app.conf.worker_hijack_root_logger is False
