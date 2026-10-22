from django.db import IntegrityError, transaction
from django.forms.models import model_to_dict
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import action
from rest_framework.response import Response

from core.auditoria import registrar
from core.models import RegistroAuditoria
from finanzas.api.views import DelHogarViewSet
from tickets import services
from tickets.models import Ticket

from .serializers import (
    ConfirmarTicketSerializer,
    ReprocesarTicketSerializer,
    SubirTicketSerializer,
    TicketSerializer,
    UrlArchivoSerializer,
)


class TicketViewSet(DelHogarViewSet):
    """Tickets del hogar. Subir responde 202: el procesado (OCR + IA) ocurre en segundo plano."""

    modelo = Ticket
    serializer_class = TicketSerializer
    http_method_names = ["get", "post", "delete", "head", "options"]  # un ticket no se edita: se confirma
    filterset_fields = ["estado", "cuenta"]
    search_fields = ["nombre_original", "texto_ocr"]
    ordering_fields = ["creado"]
    ordering = ["-creado"]

    def get_queryset(self):
        return super().get_queryset().select_related("movimiento").prefetch_related("lineas")

    def get_serializer_class(self):
        return {
            "create": SubirTicketSerializer,
            "confirmar": ConfirmarTicketSerializer,
            "reprocesar": ReprocesarTicketSerializer,
        }.get(self.action, TicketSerializer)

    def get_throttles(self):
        # límite "subidas" (60/h) solo en lo que dispara OCR + IA, que cuesta CPU y dinero
        self.throttle_scope = "subidas" if self.action in ("create", "reprocesar") else None
        return super().get_throttles()

    def _respuesta(self, ticket, codigo=status.HTTP_200_OK):
        return Response(TicketSerializer(ticket, context=self.get_serializer_context()).data, status=codigo)

    @extend_schema(responses={202: TicketSerializer})
    def create(self, request, *args, **kwargs):
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                ticket = services.subir(hogar=self.hogar, usuario=request.user, **entrada.validated_data)
        except IntegrityError as error:
            # Dos subidas simultáneas del mismo archivo pasan las dos la validación: decide la constraint
            if "ticket_archivo_unico_por_hogar" not in str(error):
                raise
            raise serializers.ValidationError({"archivo": "Este ticket ya se subió."}) from None
        return self._respuesta(ticket, status.HTTP_202_ACCEPTED)

    def perform_destroy(self, instance):
        with transaction.atomic():
            services.borrar(instance)

    @extend_schema(request=ConfirmarTicketSerializer, responses={200: TicketSerializer})
    @action(detail=True, methods=["post"])
    def confirmar(self, request, *args, **kwargs):
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        ticket = services.confirmar(self.get_object(), datos=entrada.validated_data, usuario=request.user)
        return self._respuesta(self.get_queryset().get(pk=ticket.pk))

    @extend_schema(request=ReprocesarTicketSerializer, responses={202: TicketSerializer})
    @action(detail=True, methods=["post"])
    def reprocesar(self, request, *args, **kwargs):
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        ticket = self.get_object()
        antes = model_to_dict(ticket)
        with transaction.atomic():  # se audita igual que desde el backoffice (módulo 79)
            ticket = services.reprocesar(ticket, **entrada.validated_data)
            registrar(ticket, RegistroAuditoria.Accion.MODIFICAR, request.user, antes=antes)
        return self._respuesta(ticket, status.HTTP_202_ACCEPTED)

    @extend_schema(responses={200: UrlArchivoSerializer})
    @action(detail=True, methods=["get"])
    def archivo(self, request, *args, **kwargs):
        """URL temporal del archivo (firmada en S3/R2: caduca sola). Un <img> no puede enviar el JWT."""
        return Response({"url": request.build_absolute_uri(self.get_object().archivo.url)})
