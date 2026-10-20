"""API del backoffice: lo que el equipo de soporte necesita, para TODOS los hogares, desde la propia app.

Las acciones llaman a los mismos servicios que la API de los usuarios (mismas reglas, señales y tareas)
y quedan registradas en la auditoría con el usuario de soporte que las hizo.
"""

from datetime import datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.forms.models import model_to_dict
from django.utils import timezone
from django_celery_beat.models import PeriodicTask
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import AccessToken

from backoffice import salud
from backoffice import services as backoffice
from backoffice.permisos import EsPersonal, PermisosPorAccion
from core.auditoria import registrar
from core.consultas import contar
from core.models import RegistroAuditoria
from finanzas.models import Categoria, Comercio, Movimiento
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
SUPLANTACION = timedelta(minutes=5)
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
        inicio_mes = timezone.make_aware(datetime.combine(timezone.localdate().replace(day=1), time.min))
        ia_mes = Ticket.objects.filter(procesado_en__gte=inicio_mes).aggregate(
            tickets=Count("id"),
            tokens_entrada=Coalesce(Sum("tokens_entrada"), 0),
            tokens_salida=Coalesce(Sum("tokens_salida"), 0),
        )
        datos = {
            "celery": salud.salud_colas(),
            "ia_mes": ia_mes,
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
        "suplantar": ["usuarios.view_usuario", "usuarios.suplantar_usuario"],
    }
    http_method_names = ["get", "post", "patch", "head", "options"]
    queryset = get_user_model().objects.order_by("-fecha_alta")
    filterset_fields = ["is_active", "is_staff"]
    search_fields = ["email", "nombre", "apellidos"]

    @extend_schema(request=s.SuplantarSerializer, responses={201: s.TokenSuplantacionSerializer})
    @action(detail=True, methods=["post"])
    def suplantar(self, request, *args, **kwargs):
        """Un access token de 5 minutos, de SOLO LECTURA, para ver la app como este usuario (soporte).

        Sin refresh token: cuando caduca, se acabó. No se puede suplantar a personal (escalada de privilegios).
        """
        objetivo = self.get_object()
        if objetivo.is_staff or objetivo == request.user or not objetivo.is_active:
            raise ValidationError({"usuario": ["Solo se puede suplantar a usuarios normales y activos."]})
        datos = s.SuplantarSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        token = AccessToken.for_user(objetivo)
        token.set_exp(lifetime=SUPLANTACION)
        token["suplantado_por"] = request.user.pk  # JWTConSuplantacion: solo lectura y log de cada petición
        RegistroAuditoria.objects.create(
            usuario=request.user,
            accion=RegistroAuditoria.Accion.SUPLANTAR,
            content_type=ContentType.objects.get_for_model(objetivo),
            object_id=str(objetivo.pk),
            representacion=str(objetivo),
            cambios={"motivo": datos.validated_data["motivo"], "jti": token["jti"]},
        )
        caduca = int(SUPLANTACION.total_seconds())
        return Response({"access": str(token), "caduca_en": caduca}, status=status.HTTP_201_CREATED)

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


class ComercioSoporteViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Comercios (globales) con su uso, para detectar y fusionar duplicados."""

    serializer_class = s.ComercioSoporteSerializer
    permission_classes = PERSONAL
    permisos_por_accion = {
        "list": ["finanzas.view_comercio"],
        "fusionar": ["finanzas.change_comercio", "finanzas.delete_comercio", "finanzas.change_movimiento"],
    }
    search_fields = ["nombre", "nif"]
    ordering = ["nombre"]

    def get_queryset(self):
        return Comercio.objects.annotate(num_movimientos=contar(Movimiento, "comercio"))

    @extend_schema(request=s.FusionarComerciosSerializer, responses=s.ResultadoFusionSerializer)
    @action(detail=False, methods=["post"])
    def fusionar(self, request, *args, **kwargs):
        datos = s.FusionarComerciosSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        return Response(backoffice.fusionar_comercios(usuario=request.user, **datos.validated_data))


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
