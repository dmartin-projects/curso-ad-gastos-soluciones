import pytest


@pytest.mark.django_db
def test_health(client, mocker):
    assert client.get("/health/live/").json() == {"ok": True}
    assert client.get("/health/ready/").json() == {"db": "ok", "cache": "ok"}

    mocker.patch("core.views.cache.set", side_effect=ConnectionError("Redis caído"))
    r = client.get("/health/ready/")
    assert r.status_code == 503 and r.json()["cache"] == "error"  # el proxy/Docker deja de enviarle tráfico
