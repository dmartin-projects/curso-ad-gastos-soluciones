"""API del backoffice: lo que el equipo de soporte necesita, para TODOS los hogares, desde la propia app.

Las acciones llaman a los mismos servicios que la API de los usuarios (mismas reglas, señales y tareas)
y quedan registradas en la auditoría con el usuario de soporte que las hizo.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Count, Q
from django.forms.models import model_to_dict
from django.utils import timezone
from django_celery_beat.models import PeriodicTask
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from backoffice.permisos import EsPersonal, PermisosPorAccion
from core.auditoria import registrar
from core.consultas import contar
from core.models import RegistroAuditoria
from finanzas.models import Categoria, Movimiento
from finanzas.signals import movimientos_cambiados
from hogares.models import Hogar, Membresia
from importaciones import services as importaciones
from importaciones.exceptions import EstadoNoPermitido as ImportacionNoDeshacible
from importaciones.models import Importacion
from tickets import services as tickets
from tickets.exceptions import EstadoNoPermitido as TicketNoReprocesable
from tickets.models import Ticket

from . import serializers as s

PERSONAL = [IsAuthenticated, EsPersonal, PermisosPorAccion]
ATASCADO = timedelta(minutes=15)
M = RegistroAuditoria.Accion.MODIFICAR


def _ticket_atascado():
    return Q(estado__in=[Ticket.Estado.PENDIENTE, Ticket.Estado.PROCESANDO], actualizado__lt=timezone.now() - ATASCADO)


class ResumenView(APIView):
    """La primera pantalla de soporte: ¿va todo bien?"""

    permission_classes = PERSONAL
    permisos_por_accion = {None: ["tickets.view_ticket", "importaciones.view_importacion"]}

    @extend_schema(responses=s.ResumenSerializer)
    def get(self, request, *args, **kwargs):
        ahora = timezone.now()
        por_estado = (
            Ticket.objects.filter(creado__gte=ahora - timedelta(hours=24))
            .values("estado")
            .annotate(total=Count("id"))
            .order_by("estado")
        )
        importaciones_qs = Importacion.objects.aggregate(
            en_curso=Count("id", filter=Q(estado__in=["pendiente", "analizando", "importando"])),
            con_error=Count("id", filter=Q(estado="error", creado__gte=ahora - timedelta(days=7))),
        )
        datos = {
            "tickets_24h": [{"clave": f["estado"], "total": f["total"]} for f in por_estado],
            "tickets_atascados": Ticket.objects.filter(_ticket_atascado()).count(),
            "importaciones_en_curso": importaciones_qs["en_curso"],
            "importaciones_con_error_7d": importaciones_qs["con_error"],
            "hogares": Hogar.objects.count(),
            "usuarios_activos": get_user_model().objects.filter(is_active=True).count(),
        }
        return Response(s.ResumenSerializer(datos).data)


class TicketSoporteViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.TicketSoporteSerializer
    permission_classes = PERSONAL
    permisos_por_accion = {
        "list": ["tickets.view_ticket"],
        "retrieve": ["tickets.view_ticket"],
        "reprocesar": ["tickets.change_ticket"],
    }
    filterset_fields = ["estado", "hogar"]
    search_fields = ["=id", "hogar__nombre", "subido_por__email"]
    ordering = ["-creado"]

    def get_queryset(self):
        qs = Ticket.objects.select_related("hogar", "subido_por")
        if self.request.query_params.get("atascado") == "true":
            qs = qs.filter(_ticket_atascado())
        return qs

    @extend_schema(
        parameters=[OpenApiParameter("atascado", bool, description="Más de 15 min sin terminar")],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(request=s.IdsSerializer, responses=s.ResultadoLoteSerializer)
    @action(detail=False, methods=["post"])
    def reprocesar(self, request, *args, **kwargs):
        """Reprocesa varios tickets (los que no estén en error o en revisión se omiten)."""
        ids = s.IdsSerializer(data=request.data)
        ids.is_valid(raise_exception=True)
        hechos = omitidos = 0
        for ticket in Ticket.objects.filter(pk__in=ids.validated_data["ids"]):
            antes = model_to_dict(ticket)
            try:
                with transaction.atomic():
                    ticket = tickets.reprocesar(ticket)
                    registrar(ticket, M, request.user, antes=antes)
                hechos += 1
            except TicketNoReprocesable:
                omitidos += 1
        return Response({"hechos": hechos, "omitidos": omitidos})


class ImportacionSoporteViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.ImportacionSoporteSerializer
    permission_classes = PERSONAL
    permisos_por_accion = {
        "list": ["importaciones.view_importacion"],
        "retrieve": ["importaciones.view_importacion"],
        "deshacer": ["importaciones.change_importacion"],
    }
    filterset_fields = ["estado", "hogar"]
    search_fields = ["=id", "hogar__nombre", "nombre_original"]
    ordering = ["-creado"]
    queryset = Importacion.objects.select_related("hogar")

    @extend_schema(request=None, responses=s.ImportacionSoporteSerializer)
    @action(detail=True, methods=["post"])
    def deshacer(self, request, *args, **kwargs):
        importacion = self.get_object()
        antes = model_to_dict(importacion)
        try:
            with transaction.atomic():
                importacion = importaciones.deshacer(importacion)
                registrar(importacion, M, request.user, antes=antes)
        except ImportacionNoDeshacible as e:
            raise ValidationError({"estado": [str(e)]}) from e
        return Response(self.get_serializer(importacion).data)


class HogarSoporteViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = PERSONAL
    permisos_por_accion = {"list": ["hogares.view_hogar"], "retrieve": ["hogares.view_hogar", "hogares.view_membresia"]}
    search_fields = ["nombre", "=id", "membresias__usuario__email"]
    ordering_fields = ["creado", "num_movimientos"]
    ordering = ["-creado"]

    def get_queryset(self):
        qs = Hogar.objects.annotate(
            num_miembros=contar(Membresia, "hogar"), num_movimientos=contar(Movimiento, "hogar")
        )
        if self.action == "retrieve":
            qs = qs.prefetch_related("membresias__usuario")
        return qs.distinct() if self.request.query_params.get("search") else qs  # el JOIN de la búsqueda duplica

    def get_serializer_class(self):
        return s.HogarDetalleSoporteSerializer if self.action == "retrieve" else s.HogarSoporteSerializer


class UsuarioSoporteViewSet(mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    """Ver usuarios; activar o desactivar (solo quien tenga usuarios.change_usuario, no el grupo Soporte)."""

    serializer_class = s.UsuarioSoporteSerializer
    permission_classes = PERSONAL
    permisos_por_accion = {
        "list": ["usuarios.view_usuario"],
        "retrieve": ["usuarios.view_usuario"],
        "partial_update": ["usuarios.change_usuario"],
    }
    http_method_names = ["get", "patch", "head", "options"]
    queryset = get_user_model().objects.order_by("-fecha_alta")
    filterset_fields = ["is_active", "is_staff"]
    search_fields = ["email", "nombre", "apellidos"]

    def perform_update(self, serializer):
        if serializer.instance == self.request.user:
            raise ValidationError({"is_active": ["No puedes desactivar tu propia cuenta."]})
        antes = model_to_dict(serializer.instance, fields=["is_active"])
        usuario = serializer.save()
        # un usuario desactivado deja de poder usar su access token en la siguiente petición:
        # JWTAuthentication rechaza a los usuarios inactivos (módulo 35)
        registrar(usuario, M, self.request.user, antes=antes)


class MovimientoSoporteViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = s.MovimientoSoporteSerializer
    permission_classes = PERSONAL
    permisos_por_accion = {
        "list": ["finanzas.view_movimiento"],
        "retrieve": ["finanzas.view_movimiento"],
        "recategorizar": ["finanzas.change_movimiento"],
    }
    filterset_fields = ["hogar", "revisado", "origen", "categoria"]
    search_fields = ["concepto", "comercio__nombre"]
    ordering = ["-fecha", "-id"]
    queryset = Movimiento.objects.select_related("categoria")

    @extend_schema(request=s.RecategorizarSoporteSerializer, responses=s.ResultadoLoteSerializer)
    @action(detail=False, methods=["post"])
    def recategorizar(self, request, *args, **kwargs):
        datos = s.RecategorizarSoporteSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        categoria = Categoria.objects.filter(pk=datos.validated_data["categoria"]).first()
        if categoria is None:
            raise ValidationError({"categoria": ["No existe."]})
        ids = datos.validated_data["ids"]
        with transaction.atomic():
            del_hogar = Movimiento.objects.filter(pk__in=ids, hogar_id=categoria.hogar_id)  # nunca de otro hogar
            antes = {m.pk: model_to_dict(m) for m in del_hogar}
            meses = {datos["fecha"].replace(day=1) for datos in antes.values()}
            n = del_hogar.update(categoria=categoria, revisado=True)
            for mov in Movimiento.objects.filter(pk__in=antes):
                registrar(mov, M, request.user, antes=antes[mov.pk])
            transaction.on_commit(
                lambda: movimientos_cambiados.send(sender=Movimiento, hogar_id=categoria.hogar_id, meses=meses)
            )
        return Response({"hechos": n, "omitidos": len(set(ids)) - n})


class AuditoriaViewSet(viewsets.ReadOnlyModelViewSet):
    """Solo lectura, también para el superusuario: una auditoría que se puede editar no sirve."""

    serializer_class = s.AuditoriaSerializer
    permission_classes = PERSONAL
    permisos_por_accion = {"list": ["core.view_registroauditoria"], "retrieve": ["core.view_registroauditoria"]}
    filterset_fields = ["accion", "object_id"]
    search_fields = ["representacion", "usuario__email"]
    queryset = RegistroAuditoria.objects.select_related("usuario", "content_type")

    @extend_schema(parameters=[OpenApiParameter("modelo", str, description="app.modelo, p. ej. finanzas.movimiento")])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset()
        if modelo := self.request.query_params.get("modelo"):
            app, _, nombre = modelo.partition(".")
            qs = qs.filter(content_type__app_label=app, content_type__model=nombre)
        return qs


class TareaProgramadaViewSet(mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    """Las tareas de Celery Beat (DatabaseScheduler): verlas y pausarlas/reanudarlas."""

    serializer_class = s.TareaProgramadaSerializer
    permission_classes = PERSONAL
    permisos_por_accion = {
        "list": ["django_celery_beat.view_periodictask"],
        "retrieve": ["django_celery_beat.view_periodictask"],
        "partial_update": ["django_celery_beat.change_periodictask"],
    }
    http_method_names = ["get", "patch", "head", "options"]
    queryset = PeriodicTask.objects.select_related("crontab").order_by("name")
    pagination_class = None

    def perform_update(self, serializer):
        antes = model_to_dict(serializer.instance, fields=["enabled"])
        tarea = serializer.save()  # PeriodicTask.save avisa a Beat de que la programación cambió
        registrar(tarea, M, self.request.user, antes=antes)
