import json

from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

from .urls import urlpatterns as urls_normales


@csrf_exempt
def ia_falsa(request):
    """Responde siempre el mismo ticket (lo que leería un modelo de verdad de la foto de ejemplo)."""
    datos = {
        "comercio": "Mercadona",
        "nif": "",
        "fecha": "2026-10-12",
        "total": 4.85,
        "moneda": "EUR",
        "categoria": "Supermercado",
        "lineas": [{"descripcion": "Leche", "cantidad": 1, "precio_unitario": 4.85}],
        "confianza": 0.95,
    }
    return JsonResponse({"choices": [{"message": {"role": "assistant", "content": json.dumps(datos)}}]})


# en E2E los archivos están en disco (en producción, URLs firmadas de S3/R2): Django los sirve con DEBUG
urlpatterns = [
    path("e2e/ia/chat/completions", ia_falsa),
    *urls_normales,
    *static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT),
]
