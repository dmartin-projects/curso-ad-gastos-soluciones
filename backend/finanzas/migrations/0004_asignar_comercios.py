import re
from collections import defaultdict
import unicodedata

from django.db import migrations

# Copia CONGELADA de finanzas.normalizacion.normalizar: si mañana cambia la función, esta migración
# debe seguir haciendo lo mismo que hizo el día que se escribió (por eso no se importa).
_RUIDO = re.compile(
    r"\b(s a u|s l u|s a|s l|sau|slu|sa|sl|sociedad|compra|tarj|tarjeta|pago|cargo|recibo|ref|n|\d{4,}|www|com|es)\b"
)


def normalizar(texto):
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = _RUIDO.sub(" ", t)
    return re.sub(r"\s+", " ", t).strip()


def asignar(apps, schema_editor):
    Comercio = apps.get_model("finanzas", "Comercio")
    Movimiento = apps.get_model("finanzas", "Movimiento")
    por_nombre = dict(Comercio.objects.values_list("nombre_normalizado", "id"))
    if not por_nombre:
        return
    # Se normalizan los conceptos DISTINTOS (pocos) y se hace UN update por comercio. Con el seed de
    # 50.000 movimientos, `migrate` tarda ~6 s; recorriendo fila a fila con bulk_update, ~17 s.
    conceptos_por_comercio = defaultdict(list)
    sin_comercio = Movimiento.objects.filter(comercio__isnull=True).values_list("concepto").distinct()
    for (concepto,) in sin_comercio.iterator():
        comercio_id = por_nombre.get(normalizar(concepto))
        if comercio_id:
            conceptos_por_comercio[comercio_id].append(concepto)
    for comercio_id, conceptos in conceptos_por_comercio.items():
        Movimiento.objects.filter(comercio__isnull=True, concepto__in=conceptos).update(comercio_id=comercio_id)


class Migration(migrations.Migration):
    dependencies = [("finanzas", "0003_categoria_mismo_hogar")]
    # Reversa noop: no sabemos qué movimientos ya tenían comercio antes; quitarlos todos sería destructivo.
    operations = [migrations.RunPython(asignar, migrations.RunPython.noop)]
