from django.db import migrations

# ⚠️ En una migración de datos se usan los modelos HISTÓRICOS (apps.get_model), nunca los importados:
# el código de finanzas/models.py puede cambiar en el futuro y esta migración debe seguir funcionando.
CATEGORIAS = [("Supermercado", "#2e7d32"), ("Hogar", "#6d4c41"), ("Transporte", "#1565c0"), ("Otros", "#607d8b")]


def crear(apps, schema_editor):
    Hogar = apps.get_model("hogares", "Hogar")
    Categoria = apps.get_model("finanzas", "Categoria")
    for hogar in Hogar.objects.filter(categorias__isnull=True).iterator():
        Categoria.objects.bulk_create(
            Categoria(hogar=hogar, nombre=n, color=c, orden=i) for i, (n, c) in enumerate(CATEGORIAS)
        )


class Migration(migrations.Migration):
    dependencies = [("finanzas", "0001_initial"), ("hogares", "0001_initial")]
    operations = [migrations.RunPython(crear, migrations.RunPython.noop)]
