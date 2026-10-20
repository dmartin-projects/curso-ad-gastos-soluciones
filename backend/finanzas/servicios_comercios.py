from django.contrib.postgres.search import TrigramSimilarity
from django.db import IntegrityError, transaction
from django.db.models import Count

from .models import Categoria, Comercio, Movimiento
from .normalizacion import normalizar

SIMILITUD_MINIMA = 0.4


def reconocer_comercio(texto: str) -> Comercio | None:
    """El comercio conocido más parecido al texto ("MERCADONA S.A. 1234" → Mercadona), o None.

    El filtro `trigram_similar` (operador % de pg_trgm) es el que aprovecha el índice GIN del módulo 72;
    la anotación solo sirve para ordenar los candidatos.
    """
    normalizado = normalizar(texto)
    if not normalizado:
        return None
    return (
        Comercio.objects.filter(nombre_normalizado__trigram_similar=normalizado)
        .annotate(sim=TrigramSimilarity("nombre_normalizado", normalizado))
        .filter(sim__gte=SIMILITUD_MINIMA)
        .order_by("-sim")
        .first()
    )


def reconocer_o_crear_comercio(nombre: str, nif: str = "") -> Comercio | None:
    if not normalizar(nombre):
        return None
    if comercio := reconocer_comercio(nombre):
        return comercio
    try:
        with transaction.atomic():  # savepoint: si otro proceso lo crea a la vez, la restricción única salta
            return Comercio.objects.create(nombre=nombre.strip()[:120], nif=nif)
    except IntegrityError:
        return Comercio.objects.get(nombre_normalizado=normalizar(nombre))


def sugerir_categoria(hogar, comercio: Comercio | None, nombre_sugerido: str = "") -> Categoria | None:
    """1º lo que este hogar suele elegir para ese comercio; 2º lo aprendido del comercio; 3º lo que propone la IA."""
    if comercio is not None:
        habitual = (
            Movimiento.objects.filter(hogar=hogar, comercio=comercio, categoria__isnull=False, revisado=True)
            .values("categoria")
            .annotate(veces=Count("id"))
            .order_by("-veces")
            .first()
        )
        if habitual:
            return Categoria.objects.get(pk=habitual["categoria"])
        if comercio.categoria_sugerida and (
            aprendida := Categoria.objects.filter(hogar=hogar, nombre__iexact=comercio.categoria_sugerida).first()
        ):
            return aprendida
    if nombre_sugerido:
        return Categoria.objects.filter(hogar=hogar, nombre__iexact=nombre_sugerido).first()
    return None


def aprender_categoria(comercio: Comercio | None, categoria: Categoria | None) -> bool:
    """Lo que un usuario confirma enseña al comercio (global), pero solo la primera vez.

    UPDATE condicional: dos confirmaciones simultáneas no se pisan, y una vez aprendida no cambia
    por lo que elija cada hogar (cada hogar ya tiene su propio historial, que gana siempre).
    """
    if comercio is None or categoria is None:
        return False
    return bool(
        Comercio.objects.filter(pk=comercio.pk, categoria_sugerida="").update(categoria_sugerida=categoria.nombre[:60])
    )
