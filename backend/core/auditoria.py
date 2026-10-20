from django.contrib.contenttypes.models import ContentType
from django.forms.models import model_to_dict

from .models import RegistroAuditoria

NUNCA = {"password"}  # ni siquiera el hash: la auditoría la lee el personal de soporte


def registrar(objeto, accion: str, usuario=None, antes: dict | None = None) -> RegistroAuditoria:
    """Guarda qué cambió. Solo se comparan los campos de `antes`: quien pasa uno o dos campos audita esos."""
    cambios = {}
    if antes and accion != RegistroAuditoria.Accion.BORRAR:
        despues = model_to_dict(objeto, fields=list(antes))
        cambios = {k: [str(antes[k]), str(v)] for k, v in despues.items() if k not in NUNCA and antes[k] != v}
    return RegistroAuditoria.objects.create(
        usuario=usuario if usuario and usuario.is_authenticated else None,
        accion=accion,
        content_type=ContentType.objects.get_for_model(objeto),
        object_id=str(objeto.pk),
        representacion=str(objeto)[:200],
        cambios=cambios,
    )
