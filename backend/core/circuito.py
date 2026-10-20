"""Circuit breaker compartido entre procesos (estado en la caché/Redis). Visto en el módulo 27."""

from django.core.cache import cache


class CircuitoAbierto(Exception):
    pass


class CircuitBreaker:
    def __init__(self, nombre: str, umbral: int = 5, enfriamiento: int = 60):
        self.clave_fallos = f"cb:{nombre}:fallos"
        self.clave_abierto = f"cb:{nombre}:abierto"
        self.umbral, self.enfriamiento = umbral, enfriamiento

    @property
    def abierto(self) -> bool:
        return bool(cache.get(self.clave_abierto))

    def llamar(self, funcion, *args, **kwargs):
        if self.abierto:
            raise CircuitoAbierto(self.clave_abierto)
        try:
            resultado = funcion(*args, **kwargs)
        except Exception:
            cache.add(self.clave_fallos, 0, timeout=self.enfriamiento)
            if cache.incr(self.clave_fallos) >= self.umbral:
                cache.set(self.clave_abierto, True, timeout=self.enfriamiento)
                cache.delete(self.clave_fallos)
            raise
        cache.delete(self.clave_fallos)
        return resultado
