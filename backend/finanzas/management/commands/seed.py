import random
from datetime import date, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from finanzas.models import Comercio, Cuenta, Movimiento, Presupuesto
from hogares.services import crear_hogar
from usuarios.models import Usuario

COMERCIOS = [
    ("Mercadona", "Supermercado", (-120, -8)),
    ("Lidl", "Supermercado", (-80, -5)),
    ("Repsol", "Combustible", (-70, -30)),
    ("Metro de Madrid", "Transporte público", (-20, -2)),
    ("Netflix", "Suscripciones", (-13, -13)),
    ("Farmacia Sol", "Farmacia", (-35, -4)),
    ("Bar Manolo", "Restaurantes", (-45, -6)),
    ("Zara", "Ropa", (-90, -15)),
]


class Command(BaseCommand):
    help = "Crea un usuario demo con un hogar y movimientos de ejemplo (solo desarrollo)."

    def add_arguments(self, parser):
        parser.add_argument("--movimientos", type=int, default=2000)
        parser.add_argument("--email", default="demo@example.com")

    @transaction.atomic
    def handle(self, *args, movimientos, email, **opciones):
        usuario, creado = Usuario.objects.get_or_create(email=email, defaults={"nombre": "Demo", "is_active": True})
        if creado:
            usuario.set_password("demo12345-demo")
            usuario.save()
        hogar = crear_hogar(usuario=usuario, nombre="Casa demo")
        cuenta = Cuenta.objects.create(hogar=hogar, nombre="Cuenta común")
        categorias = {c.nombre: c for c in hogar.categorias.all()}
        comercios = [(Comercio.objects.get_or_create(nombre=n)[0], cat, r) for n, cat, r in COMERCIOS]

        hoy = date.today()
        nuevos = []
        for _ in range(movimientos):
            comercio, cat, (minimo, maximo) = random.choice(comercios)
            importe = Decimal(random.uniform(minimo, maximo)).quantize(Decimal("0.01"))
            nuevos.append(
                Movimiento(
                    hogar=hogar,
                    cuenta=cuenta,
                    fecha=hoy - timedelta(days=random.randint(0, 540)),
                    importe=importe,
                    concepto=comercio.nombre.upper(),
                    comercio=comercio,
                    categoria=categorias.get(cat),
                    creado_por=usuario,
                )
            )
        for mes in range(18):  # nóminas
            dia = (hoy.replace(day=1) - timedelta(days=30 * mes)).replace(day=28)
            nuevos.append(
                Movimiento(
                    hogar=hogar,
                    cuenta=cuenta,
                    fecha=dia,
                    importe=Decimal("2150.00"),
                    concepto="NOMINA",
                    categoria=categorias["Nómina"],
                    creado_por=usuario,
                )
            )
        Movimiento.objects.bulk_create(nuevos, batch_size=1000)
        Presupuesto.objects.create(
            hogar=hogar, categoria=categorias["Supermercado"], mes=hoy.replace(day=1), importe=Decimal("400")
        )
        self.stdout.write(self.style.SUCCESS(f"Hogar {hogar.pk} con {len(nuevos)} movimientos para {email}"))
