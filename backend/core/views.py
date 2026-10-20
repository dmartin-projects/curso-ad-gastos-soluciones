from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse


def health_live(request):
    """¿El proceso responde? (liveness)"""
    return JsonResponse({"ok": True})


def health_ready(request):
    """¿Puede atender? Comprueba base de datos y caché (readiness)."""
    estado = {}
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
        estado["db"] = "ok"
    except Exception:
        estado["db"] = "error"
    try:
        cache.set("health", 1, 5)
        estado["cache"] = "ok" if cache.get("health") == 1 else "error"
    except Exception:
        estado["cache"] = "error"
    ok = all(v == "ok" for v in estado.values())
    return JsonResponse(estado, status=200 if ok else 503)
