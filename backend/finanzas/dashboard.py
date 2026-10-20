"""Datos del dashboard de un mes: agregaciones en la base de datos (nunca bucles en Python sobre movimientos)."""

import calendar
import logging
import time
from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.core.cache import cache
from django.db.models import Count, F, Q, Sum, Window
from django.db.models.functions import Coalesce, Rank, TruncMonth
from django.utils import timezone

from .models import Categoria, Movimiento, Presupuesto
from .querysets import rango_mes

logger = logging.getLogger(__name__)
CERO = Decimal("0")
DURACION_CACHE = 60 * 60  # 1 h: de todos modos se invalida en cuanto cambia algo


def hoy(hogar) -> date:
    """La fecha de hoy en la zona horaria del hogar."""
    return timezone.localdate(timezone=ZoneInfo(hogar.zona_horaria))


def mes_actual(hogar) -> date:
    """El mes "de hoy" en la zona horaria del hogar: a las 00:30 del día 1 en Madrid aún es el mes anterior en UTC."""
    return timezone.localdate(timezone=ZoneInfo(hogar.zona_horaria)).replace(day=1)


def mes_anterior(mes: date) -> date:
    return date(mes.year - (mes.month == 1), (mes.month - 2) % 12 + 1, 1)


def _totales(hogar, mes: date) -> dict:
    """Totales del mes y del anterior en UNA consulta: agregación condicional (Sum(..., filter=Q(...)), módulo 07)."""
    anterior, fin = mes_anterior(mes), rango_mes(mes)[1]
    este_mes, mes_previo = Q(fecha__gte=mes), Q(fecha__lt=mes)
    return (
        Movimiento.objects.del_hogar(hogar)
        .filter(fecha__gte=anterior, fecha__lt=fin)  # el índice (hogar, -fecha) acota a dos meses
        .aggregate(
            gastos=Coalesce(Sum("importe", filter=este_mes & Q(importe__lt=0)), CERO),
            ingresos=Coalesce(Sum("importe", filter=este_mes & Q(importe__gt=0)), CERO),
            num=Count("id", filter=este_mes),
            gastos_antes=Coalesce(Sum("importe", filter=mes_previo & Q(importe__lt=0)), CERO),
        )
    )


def por_categoria(movimientos) -> list[dict]:
    """Gasto por categoría PRINCIPAL: las subcategorías suman en su padre (Coalesce(padre, categoría))."""
    filas = (
        movimientos.gastos()
        .annotate(principal=Coalesce("categoria__padre", "categoria"))
        .values("principal")
        .annotate(total=Sum("importe"))
        .order_by("total")  # negativos: el mayor gasto primero
    )
    nombres = {c.pk: c for c in Categoria.objects.filter(pk__in=[f["principal"] for f in filas if f["principal"]])}
    total = sum(f["total"] for f in filas) or Decimal("1")
    return [
        {
            "categoria": f["principal"],
            "nombre": nombres[f["principal"]].nombre if f["principal"] else "Sin categoría",
            "color": nombres[f["principal"]].color if f["principal"] else "#9e9e9e",
            "total": -f["total"],
            "porcentaje": round(f["total"] * 100 / total, 1),
        }
        for f in filas
    ]


def acumulado_diario(movimientos) -> list[dict]:
    """Gasto de cada día y acumulado del mes con funciones de ventana (módulo 11).

    Ventana con marco RANGE (el de por defecto con ORDER BY): las filas del mismo día son "pares" y
    comparten el acumulado del final del día. Por eso basta un DISTINCT sobre (fecha, dia, acumulado).
    """
    return list(
        movimientos.gastos()
        .annotate(
            dia=Window(Sum("importe"), partition_by=[F("fecha")]),
            acumulado=Window(Sum("importe"), order_by=F("fecha").asc()),
        )
        .values("fecha", "dia", "acumulado")
        .order_by("fecha")
        .distinct()
    )


def comparativa_diaria(hogar, mes: date, acumulado: list[dict]) -> list[dict]:
    """Acumulado de este mes y del anterior, día 1 con día 1: las dos líneas del gráfico.

    `acumulado` es el de este mes (ya calculado); solo hace falta UNA consulta más, la del mes anterior.
    Los días sin gasto repiten el acumulado anterior (la línea no baja a 0) y los días que aún
    no han llegado van a None (la línea se corta en "hoy").
    """
    anterior = mes_anterior(mes)
    este = {f["fecha"].day: -f["acumulado"] for f in acumulado}
    antes = {
        f["fecha"].day: -f["acumulado"] for f in acumulado_diario(Movimiento.objects.del_hogar(hogar).del_mes(anterior))
    }
    dias_este = calendar.monthrange(mes.year, mes.month)[1]
    dias_antes = calendar.monthrange(anterior.year, anterior.month)[1]
    hoy_ = hoy(hogar)
    hasta = hoy_.day if (hoy_.year, hoy_.month) == (mes.year, mes.month) else dias_este
    filas, a, b = [], CERO, CERO
    for dia in range(1, max(dias_este, dias_antes) + 1):
        a, b = este.get(dia, a), antes.get(dia, b)
        filas.append(
            {"dia": dia, "este_mes": a if dia <= hasta else None, "mes_anterior": b if dia <= dias_antes else None}
        )
    return filas


def ranking(hogar, mes: date, meses_atras: int = 12) -> list[dict]:
    """Para cada categoría con gasto este mes: en qué puesto queda frente a los 12 meses anteriores (1 = el que más).

    GROUP BY (categoría principal, mes) y, SOBRE ese resultado, Rank() particionado por categoría.
    La ventana se calcula después de agrupar: por eso puede ordenar por la suma.
    """
    desde = mes
    for _ in range(meses_atras):
        desde = mes_anterior(desde)
    filas = (
        Movimiento.objects.del_hogar(hogar)
        .gastos()
        .filter(fecha__gte=desde, fecha__lt=rango_mes(mes)[1])
        .annotate(principal=Coalesce("categoria__padre", "categoria"), m=TruncMonth("fecha"))
        .values("principal", "m")
        .annotate(total=Sum("importe"))
        .annotate(
            posicion=Window(Rank(), partition_by=F("principal"), order_by=F("total").asc()),  # negativos
            meses=Window(Count("principal"), partition_by=F("principal")),
        )
        .order_by()
    )
    # Filtrar por mes en SQL iría al WHERE, ANTES de la ventana, y cada categoría quedaría sola (puesto 1).
    # Son ≤ 13 filas por categoría: se elige el mes en Python.
    de_este_mes = [f for f in filas if f["m"] == mes and f["principal"]]
    nombres = dict(Categoria.objects.filter(pk__in=[f["principal"] for f in de_este_mes]).values_list("pk", "nombre"))
    return sorted(
        (
            {
                "categoria": f["principal"],
                "nombre": nombres[f["principal"]],
                "posicion": f["posicion"],
                "de": f["meses"],
            }
            for f in de_este_mes
        ),
        key=lambda r: (r["posicion"], r["nombre"]),
    )


def evolucion(hogar, hasta: date, meses: int = 12) -> list[dict]:
    desde = hasta
    for _ in range(meses - 1):
        desde = mes_anterior(desde)
    filas = (
        Movimiento.objects.del_hogar(hogar)
        .filter(fecha__gte=desde, fecha__lt=rango_mes(hasta)[1])
        .annotate(mes=TruncMonth("fecha"))
        .values("mes")
        .annotate(
            gastos=Coalesce(Sum("importe", filter=Q(importe__lt=0)), CERO),
            ingresos=Coalesce(Sum("importe", filter=Q(importe__gt=0)), CERO),
        )
        .order_by("mes")
    )
    por_mes = {f["mes"]: f for f in filas}
    resultado, mes = [], desde
    while mes <= hasta:  # rellena los meses sin movimientos con ceros (el gráfico necesita los 12)
        fila = por_mes.get(mes, {"gastos": CERO, "ingresos": CERO})
        resultado.append({"mes": mes, "gastos": -fila["gastos"], "ingresos": fila["ingresos"]})
        mes = rango_mes(mes)[1]
    return resultado


def calcular(hogar, mes: date) -> dict:
    del_mes = Movimiento.objects.del_hogar(hogar).del_mes(mes)
    t = _totales(hogar, mes)
    gastos, gastos_antes = -t["gastos"], -t["gastos_antes"]
    acumulado = acumulado_diario(del_mes)
    return {
        "mes": mes,
        "gastos": gastos,
        "ingresos": t["ingresos"],
        "balance": t["ingresos"] - gastos,
        "num_movimientos": t["num"],
        "gastos_mes_anterior": gastos_antes,
        "variacion": round((gastos - gastos_antes) * 100 / gastos_antes, 1) if gastos_antes else None,
        "por_categoria": por_categoria(del_mes),
        "acumulado": [{"fecha": f["fecha"], "gasto": -f["dia"], "acumulado": -f["acumulado"]} for f in acumulado],
        "comparativa": comparativa_diaria(hogar, mes, acumulado),
        "ranking": ranking(hogar, mes),
        "evolucion": evolucion(hogar, mes),
        "top_comercios": list(
            del_mes.gastos()
            .filter(comercio__isnull=False)
            .values("comercio", nombre=F("comercio__nombre"))
            .annotate(total=-Sum("importe"), veces=Count("id"))
            .order_by("-total")[:5]
        ),
        "presupuestos": [
            {
                "categoria": p.categoria.nombre,
                "importe": p.importe,
                "gastado": -p.gastado,
                "porcentaje": int(-p.gastado * 100 / p.importe),
            }
            for p in Presupuesto.objects.filter(hogar=hogar, mes=mes).con_gastado().select_related("categoria")
        ],
        "pendientes_revision": Movimiento.objects.del_hogar(hogar).pendientes_revision().count(),
    }


# ── Caché con versión por hogar ──
def _clave_version(hogar_id: int) -> str:
    return f"dashboard:version:{hogar_id}"


def _inicial() -> int:
    # Empieza en "ahora" (ms), no en 1: si Redis expulsa la clave por falta de memoria, la versión nueva
    # nunca coincide con una antigua cuyos datos sigan en la caché.
    return time.time_ns() // 1_000_000


def version(hogar_id: int) -> int:
    clave = _clave_version(hogar_id)
    cache.add(clave, _inicial(), timeout=None)  # no caduca: es solo un contador
    return cache.get(clave) or _inicial()


def invalidar(hogar_id: int) -> None:
    """O(1): no hay que buscar ni borrar claves; las de versiones anteriores caducan solas."""
    clave = _clave_version(hogar_id)
    cache.add(clave, _inicial(), timeout=None)
    cache.incr(clave)  # atómico en Redis


def _calcular_midiendo(hogar, mes: date) -> dict:
    inicio = time.perf_counter()
    datos = calcular(hogar, mes)
    ms = (time.perf_counter() - inicio) * 1000
    # en el mensaje para leerlo en consola; en `extra` para filtrar/agregar con LOG_FORMAT=json (módulo 30)
    logger.info(
        "Dashboard %s de %s calculado en %.1f ms",
        f"{mes:%Y-%m}",
        hogar.pk,
        ms,
        extra={"hogar_id": hogar.pk, "mes": f"{mes:%Y-%m}", "duracion_ms": round(ms, 1)},
    )
    return datos


def clave(hogar_id: int, v: int, mes: date) -> str:
    return f"dashboard:{hogar_id}:v{v}:{mes:%Y-%m}"


def obtener(hogar, mes: date) -> tuple[dict, int]:
    v = version(hogar.pk)
    datos = cache.get_or_set(clave(hogar.pk, v, mes), lambda: _calcular_midiendo(hogar, mes), DURACION_CACHE)
    return datos, v
