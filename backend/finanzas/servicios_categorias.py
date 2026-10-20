from django.db import transaction

from .models import Categoria

# (nombre, color, icono, [subcategorías])
CATEGORIAS_POR_DEFECTO = [
    ("Supermercado", "#2e7d32", "shopping_cart", []),
    ("Hogar", "#6d4c41", "home", ["Alquiler / hipoteca", "Luz", "Agua", "Gas", "Internet y móvil"]),
    ("Transporte", "#1565c0", "directions_car", ["Combustible", "Transporte público", "Parking"]),
    ("Restaurantes", "#ef6c00", "restaurant", []),
    ("Salud", "#c62828", "medical_services", ["Farmacia"]),
    ("Ocio", "#8e24aa", "theaters", ["Suscripciones", "Viajes"]),
    ("Ropa", "#ad1457", "checkroom", []),
    ("Educación", "#00838f", "school", []),
    ("Otros", "#607d8b", "category", []),
]
INGRESOS_POR_DEFECTO = [("Nómina", "#1b5e20", "payments"), ("Otros ingresos", "#33691e", "savings")]


@transaction.atomic
def crear_categorias_por_defecto(hogar) -> int:
    creadas = 0
    for orden, (nombre, color, icono, hijas) in enumerate(CATEGORIAS_POR_DEFECTO):
        padre = Categoria.objects.create(hogar=hogar, nombre=nombre, color=color, icono=icono, orden=orden)
        creadas += 1
        Categoria.objects.bulk_create(
            Categoria(hogar=hogar, padre=padre, nombre=h, color=color, icono=icono, orden=i)
            for i, h in enumerate(hijas)
        )
        creadas += len(hijas)
    base = len(CATEGORIAS_POR_DEFECTO)
    Categoria.objects.bulk_create(
        Categoria(hogar=hogar, nombre=n, color=c, icono=i, orden=base + k, es_ingreso=True)
        for k, (n, c, i) in enumerate(INGRESOS_POR_DEFECTO)
    )
    return creadas + len(INGRESOS_POR_DEFECTO)
