from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.paginacion import PaginacionCursor
from notificaciones import services
from notificaciones.middleware import DURACION_TICKET, crear_ticket
from notificaciones.models import Notificacion

from .serializers import LeerSerializer, NotificacionSerializer, TicketWsSerializer


class PaginacionNotificaciones(PaginacionCursor):
    page_size = 20
    ordering = ("-creado", "-id")


Contador = inline_serializer("Contador", {"no_leidas": serializers.IntegerField()})
Actualizadas = inline_serializer("Actualizadas", {"actualizadas": serializers.IntegerField()})


class NotificacionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Las notificaciones del usuario autenticado (de todos sus hogares). ?leida=false para las pendientes."""

    serializer_class = NotificacionSerializer
    pagination_class = PaginacionNotificaciones
    filterset_fields = ["leida", "tipo", "hogar"]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # drf-spectacular genera el esquema sin usuario (módulo 38)
            return Notificacion.objects.none()
        return Notificacion.objects.filter(usuario=self.request.user)

    @extend_schema(request=None, responses={204: None})
    @action(detail=True, methods=["post"])
    def leer(self, request, *args, **kwargs):
        services.marcar_leidas(request.user, [self.get_object().pk])  # get_object: 404 si no es suya
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(request=LeerSerializer, responses={200: Actualizadas})
    @action(detail=False, methods=["post"], url_path="leer-todas")
    def leer_todas(self, request, *args, **kwargs):
        """Sin `ids`, marca todas; con `ids`, solo esas."""
        datos = LeerSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        return Response({"actualizadas": services.marcar_leidas(request.user, datos.validated_data.get("ids"))})

    @extend_schema(responses={200: Contador})
    @action(detail=False, methods=["get"], url_path="no-leidas", filter_backends=[], pagination_class=None)
    def no_leidas(self, request, *args, **kwargs):
        return Response({"no_leidas": self.get_queryset().filter(leida=False).count()})


class TicketWebSocketView(APIView):
    """Ticket de un solo uso para abrir el WebSocket: el JWT nunca viaja en la URL."""

    @extend_schema(request=None, responses={201: TicketWsSerializer})
    def post(self, request, *args, **kwargs):
        return Response(
            {"ticket": crear_ticket(request.user), "caduca_en": DURACION_TICKET}, status=status.HTTP_201_CREATED
        )
