from django.conf import settings
from django.core.cache import cache


def agrupar(clave: str, segundos: int, tarea, *args) -> bool:
    """*Debounce* entre procesos: encola `tarea` dentro de `segundos`, salvo que ya haya una pendiente.

    Borrar 500 movimientos emite 500 post_delete; sin agrupar serían 500 tareas idénticas.
    `cache.add` solo escribe si la clave no existe y es atómico en Redis: el primero gana y el resto
    se descarta. Como la tarea se ejecuta al final de la ventana, ve también los cambios de los demás.
    """
    if not settings.AGRUPAR_TAREAS:  # E2E (Celery "eager"): ver config/settings/e2e.py
        tarea.apply_async(args)
        return True
    if cache.add(f"agrupar:{clave}", 1, timeout=segundos):
        tarea.apply_async(args, countdown=segundos)
        return True
    return False
