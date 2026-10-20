"""Huella de un movimiento importado: lo identifica aunque se importe otra vez (RNF4)."""

import hashlib
from collections import Counter

from finanzas.normalizacion import normalizar

from .lectores import FilaLeida


def huellas(cuenta_id: int, filas: list[FilaLeida]) -> list[str]:
    """sha256(cuenta | fecha | importe | concepto normalizado | nº de ocurrencia).

    El nº de ocurrencia distingue dos movimientos idénticos legítimos (dos cafés de 1,50 € el mismo día
    en el mismo bar): el primero es #1 y el segundo #2, en este extracto y en cualquier otro que los incluya.
    """
    vistas: Counter = Counter()
    resultado = []
    for fila in filas:
        base = (cuenta_id, fila.fecha.isoformat(), f"{fila.importe:.2f}", normalizar(fila.concepto))
        vistas[base] += 1
        texto = "|".join(map(str, (*base, vistas[base])))
        resultado.append(hashlib.sha256(texto.encode()).hexdigest())
    return resultado
