import json
from datetime import date
from decimal import Decimal

import httpx
import pytest

from core.circuito import CircuitBreaker, CircuitoAbierto
from tickets.ia import ClienteIA, ErrorRespuestaIA, ErrorTransitorioIA

from .conftest import URL_IA, datos_ia, respuesta_ia


@pytest.fixture
def cliente():
    with ClienteIA(base_url="https://ia.test/v1/", api_key="k", modelo="m") as c:
        yield c


def test_envia_esquema_con_las_categorias_del_hogar_y_valida_la_respuesta(cliente, respx_mock):
    ruta = respx_mock.post(URL_IA).mock(return_value=respuesta_ia(datos_ia()))

    datos = cliente.extraer_ticket("MERCADONA…", ["Supermercado", "Ocio"])

    cuerpo = json.loads(ruta.calls.last.request.content)
    assert ruta.calls.last.request.headers["Authorization"] == "Bearer k"
    esquema = cuerpo["response_format"]["json_schema"]["schema"]
    assert esquema["properties"]["categoria"]["enum"] == ["Supermercado", "Ocio", ""]
    assert cuerpo["temperature"] == 0
    assert len(cuerpo["messages"][1]["content"]) == 1  # sin imagen
    assert datos["total"] == Decimal("4.85") and datos["fecha"] == date(2026, 10, 12)
    assert datos["lineas"][0]["cantidad"] == Decimal("2.000")


def test_si_el_ocr_no_sirve_envia_la_imagen(cliente, respx_mock):
    ruta = respx_mock.post(URL_IA).mock(return_value=respuesta_ia(datos_ia()))
    cliente.extraer_ticket("", ["Ocio"], imagen_png=b"\x89PNG...")
    parte = json.loads(ruta.calls.last.request.content)["messages"][1]["content"][1]
    assert parte["type"] == "image_url" and parte["image_url"]["url"].startswith("data:image/png;base64,")


def test_normaliza_lo_que_devuelve_la_ia(cliente, respx_mock):
    respx_mock.post(URL_IA).mock(return_value=respuesta_ia(datos_ia(fecha="", total=4.849999)))
    datos = cliente.extraer_ticket("…", [])
    assert datos["fecha"] is None
    assert datos["total"] == Decimal("4.85")  # redondeado, no rechazado


@pytest.mark.parametrize(
    "respuesta, error",
    [
        (httpx.Response(429), ErrorTransitorioIA),
        (httpx.Response(503), ErrorTransitorioIA),
        (httpx.ConnectTimeout("lento"), ErrorTransitorioIA),
        (httpx.Response(401, json={"error": "clave"}), ErrorRespuestaIA),
        (httpx.Response(200, json={"choices": [{"message": {"content": "no es json"}}]}), ErrorRespuestaIA),
        (respuesta_ia(datos_ia(total=-3)), ErrorRespuestaIA),  # el total no puede ser negativo
        (respuesta_ia(datos_ia(confianza=7)), ErrorRespuestaIA),
    ],
)
def test_clasifica_los_errores(cliente, respx_mock, respuesta, error):
    ruta = respx_mock.post(URL_IA)
    if isinstance(respuesta, Exception):
        ruta.mock(side_effect=respuesta)
    else:
        ruta.mock(return_value=respuesta)
    with pytest.raises(error):
        cliente.extraer_ticket("…", [])


def test_circuit_breaker_deja_de_llamar_tras_el_umbral():
    llamadas = []

    def falla():
        llamadas.append(1)
        raise ErrorTransitorioIA("503")

    breaker = CircuitBreaker("prueba", umbral=3, enfriamiento=60)
    for _ in range(3):
        with pytest.raises(ErrorTransitorioIA):
            breaker.llamar(falla)
    with pytest.raises(CircuitoAbierto):
        breaker.llamar(falla)
    assert len(llamadas) == 3
