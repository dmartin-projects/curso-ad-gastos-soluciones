from django.db import transaction
from django.utils import timezone

from .exceptions import InvitacionNoValida, UltimoAdministrador, YaEsMiembro
from .models import Hogar, Invitacion, Membresia
from .signals import hogar_creado


@transaction.atomic
def crear_hogar(*, usuario, nombre: str, moneda: str = "EUR", zona_horaria: str = "Europe/Madrid") -> Hogar:
    hogar = Hogar.objects.create(nombre=nombre, moneda=moneda, zona_horaria=zona_horaria)
    Membresia.objects.create(hogar=hogar, usuario=usuario, rol=Membresia.Rol.ADMIN)
    hogar_creado.send(sender=Hogar, hogar=hogar)  # finanzas crea las categorías por defecto (módulo 72)
    return hogar


def invitar(*, hogar: Hogar, email: str, rol: str, invitado_por) -> Invitacion:
    email = email.strip().lower()
    if hogar.miembros.filter(email__iexact=email).exists():
        raise YaEsMiembro()
    invitacion, _ = Invitacion.objects.update_or_create(
        hogar=hogar,
        email=email,
        aceptada__isnull=True,
        defaults={"rol": rol, "invitado_por": invitado_por, "caduca": Invitacion._meta.get_field("caduca").default()},
    )
    from .tasks import enviar_invitacion  # evita importación circular

    transaction.on_commit(lambda: enviar_invitacion.enqueue(invitacion.pk))
    return invitacion


@transaction.atomic
def aceptar_invitacion(*, token: str, usuario) -> Membresia:
    invitacion = Invitacion.objects.select_for_update().filter(token=token).first()
    if invitacion is None or not invitacion.vigente or invitacion.email != usuario.email.lower():
        raise InvitacionNoValida()
    membresia, creada = Membresia.objects.get_or_create(
        hogar_id=invitacion.hogar_id, usuario=usuario, defaults={"rol": invitacion.rol}
    )
    if not creada:
        raise YaEsMiembro()
    invitacion.aceptada = timezone.now()
    invitacion.save(update_fields=["aceptada"])
    return membresia


@transaction.atomic
def cambiar_rol(*, membresia: Membresia, rol: str) -> Membresia:
    if membresia.rol == Membresia.Rol.ADMIN and rol != Membresia.Rol.ADMIN:
        quedan = Membresia.objects.select_for_update().filter(hogar_id=membresia.hogar_id, rol=Membresia.Rol.ADMIN)
        if quedan.count() <= 1:
            raise UltimoAdministrador()
    membresia.rol = rol
    membresia.save(update_fields=["rol"])
    return membresia
