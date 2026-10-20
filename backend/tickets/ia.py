"""Cliente de IA: convierte el texto (y si hace falta la imagen) de un ticket en datos estructurados.

Habla el formato *Chat Completions* de OpenAI, que hoy entienden casi todos los proveedores
(Gemini, OpenAI, Mistral, Groq…) y también Ollama en local. Cambiar de proveedor = cambiar
IA_BASE_URL, IA_MODELO e IA_API_KEY. El resto del proyecto solo conoce `extraer_ticket()`.
"""

import base64
import json
from decimal import ROUND_HALF_UP, Decimal

import httpx
from django.conf import settings
from rest_framework import serializers

from core.circuito import CircuitBreaker


class ErrorIA(Exception):
    pass


class ErrorTransitorioIA(ErrorIA):
    """Timeout, 429, 5xx, red: tiene sentido reintentar más tarde."""


class ErrorRespuestaIA(ErrorIA):
    """La IA respondió, pero algo no cuadra (JSON inválido, datos imposibles, 4xx): reintentar no ayuda."""


breaker_ia = CircuitBreaker("ia", umbral=5, enfriamiento=120)

INSTRUCCIONES = """Extraes datos de tickets de compra (normalmente españoles) a partir del texto de un OCR,
que puede tener errores de lectura. Reglas:
- comercio: nombre comercial corto, sin forma jurídica ni dirección ("Mercadona", no "MERCADONA S.A. C/ Mayor 3").
- fecha: AAAA-MM-DD; las fechas españolas vienen como DD/MM/AAAA. Cadena vacía si no aparece.
- total: el importe TOTAL pagado, positivo, con punto decimal. null si no lo encuentras.
- lineas: los productos con cantidad y precio unitario; no incluyas subtotales, IVA ni el total.
- categoria: una de las categorías permitidas, o cadena vacía si ninguna encaja.
- confianza: de 0 a 1, cuánto te fías de comercio, fecha y total. Baja si el texto está muy dañado.
No inventes datos: si algo no aparece, déjalo vacío."""


def esquema(categorias: list[str]) -> dict:
    """JSON Schema de la respuesta. Las categorías del hogar van como enum: la IA no puede inventarlas."""
    linea = {
        "type": "object",
        "properties": {
            "descripcion": {"type": "string"},
            "cantidad": {"type": "number"},
            "precio_unitario": {"type": "number"},
        },
        "required": ["descripcion", "cantidad", "precio_unitario"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {
            "comercio": {"type": "string"},
            "nif": {"type": "string"},
            "fecha": {"type": "string"},
            "total": {"type": ["number", "null"]},
            "moneda": {"type": "string"},
            "categoria": {"type": "string", "enum": [*categorias, ""]},
            "lineas": {"type": "array", "items": linea},
            "confianza": {"type": "number"},
        },
        "required": ["comercio", "nif", "fecha", "total", "moneda", "categoria", "lineas", "confianza"],
        "additionalProperties": False,
    }


# ── Validación: la salida de la IA es una entrada externa más; se valida igual que una petición ──
class DecimalRedondeado(serializers.DecimalField):
    """Redondea en vez de rechazar: un LLM devuelve 4.849999 donde el ticket dice 4,85.

    El parámetro `rounding` de DecimalField no basta: DRF comprueba los decimales ANTES de redondear.
    """

    def validate_precision(self, valor):
        return super().validate_precision(valor.quantize(Decimal(1).scaleb(-self.decimal_places), ROUND_HALF_UP))


class LineaIASerializer(serializers.Serializer):
    descripcion = serializers.CharField(max_length=200)
    cantidad = DecimalRedondeado(max_digits=8, decimal_places=3, min_value=Decimal("0.001"))
    precio_unitario = DecimalRedondeado(max_digits=10, decimal_places=2)


class DatosTicketSerializer(serializers.Serializer):
    comercio = serializers.CharField(max_length=120, allow_blank=True, trim_whitespace=True)
    nif = serializers.CharField(max_length=15, allow_blank=True, required=False, default="")
    fecha = serializers.DateField(allow_null=True)
    total = DecimalRedondeado(max_digits=10, decimal_places=2, min_value=Decimal("0.01"), allow_null=True)
    moneda = serializers.CharField(max_length=3, required=False, default="EUR")
    categoria = serializers.CharField(max_length=60, allow_blank=True, required=False, default="")
    lineas = LineaIASerializer(many=True, required=False, default=list)
    confianza = serializers.FloatField(min_value=0, max_value=1)

    def to_internal_value(self, datos):
        if isinstance(datos, dict) and datos.get("fecha") == "":
            datos = {**datos, "fecha": None}
        return super().to_internal_value(datos)


def validar(datos) -> dict:
    s = DatosTicketSerializer(data=datos)
    if not s.is_valid():
        raise ErrorRespuestaIA(f"Datos de la IA no válidos: {s.errors}")
    return s.validated_data


class ClienteIA:
    def __init__(self, *, base_url: str, api_key: str, modelo: str, timeout: float = 30.0):
        self.modelo = modelo
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=httpx.Timeout(timeout, connect=5.0),
        )

    @classmethod
    def desde_settings(cls) -> "ClienteIA":
        return cls(
            base_url=settings.IA_BASE_URL,
            api_key=settings.IA_API_KEY,
            modelo=settings.IA_MODELO,
            timeout=settings.IA_TIMEOUT,
        )

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._http.close()

    def extraer_ticket(self, texto: str, categorias: list[str], imagen_png: bytes | None = None) -> dict:
        contenido: list[dict] = [
            {"type": "text", "text": f"Categorías permitidas: {', '.join(categorias)}\n\nTexto del ticket:\n{texto}"}
        ]
        if imagen_png:  # el OCR no ha leído nada útil: que la IA mire la imagen (modelos multimodales)
            datos_url = "data:image/png;base64," + base64.b64encode(imagen_png).decode()
            contenido.append({"type": "image_url", "image_url": {"url": datos_url}})
        cuerpo = {
            "model": self.modelo,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": INSTRUCCIONES},
                {"role": "user", "content": contenido},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "ticket", "strict": True, "schema": esquema(categorias)},
            },
        }
        return validar(self._enviar(cuerpo))

    def _enviar(self, cuerpo: dict) -> dict:
        try:
            r = self._http.post("chat/completions", json=cuerpo)
        except httpx.TransportError as e:  # timeouts, conexión rechazada, DNS…
            raise ErrorTransitorioIA(f"Error de red: {e.__class__.__name__}") from e
        if r.status_code == 429 or r.status_code >= 500:
            raise ErrorTransitorioIA(f"HTTP {r.status_code}")
        if r.is_error:  # 400/401/403/404: petición o configuración incorrectas
            raise ErrorRespuestaIA(f"HTTP {r.status_code}: {r.text[:300]}")
        try:
            return json.loads(r.json()["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise ErrorRespuestaIA("La respuesta no contiene un JSON válido") from e
