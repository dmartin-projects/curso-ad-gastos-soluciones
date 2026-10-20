from django.db import migrations

# Django no tiene claves foráneas compuestas, pero PostgreSQL sí. Dos pasos:
# 1. (id, hogar_id) único en categoría: es el destino al que puede apuntar una FK compuesta.
# 2. FK (categoria_id, hogar_id) → categoría(id, hogar_id): la BD rechaza una categoría de otro hogar.
#    MATCH SIMPLE (el defecto): si categoria_id es NULL no se comprueba nada.
#    ON DELETE SET NULL (categoria_id): PostgreSQL ≥ 15 permite anular SOLO esa columna; sin la lista,
#    borrar una categoría intentaría poner también hogar_id a NULL y fallaría por NOT NULL.
#    DEFERRABLE INITIALLY DEFERRED, igual que las FK que crea Django.
SQL = """
ALTER TABLE finanzas_categoria
    ADD CONSTRAINT categoria_id_hogar_unico UNIQUE (id, hogar_id);
ALTER TABLE finanzas_movimiento
    ADD CONSTRAINT movimiento_categoria_mismo_hogar
    FOREIGN KEY (categoria_id, hogar_id) REFERENCES finanzas_categoria (id, hogar_id)
    ON DELETE SET NULL (categoria_id) DEFERRABLE INITIALLY DEFERRED;
"""
REVERSE = """
ALTER TABLE finanzas_movimiento DROP CONSTRAINT movimiento_categoria_mismo_hogar;
ALTER TABLE finanzas_categoria DROP CONSTRAINT categoria_id_hogar_unico;
"""


class Migration(migrations.Migration):
    dependencies = [("finanzas", "0002_categorias_hogares_existentes")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
