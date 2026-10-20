from django.db import transaction
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from finanzas.api.views import DelHogarViewSet
from hogares.models import Membresia
from importaciones import services
from importaciones.models import FilaImportacion, Importacion

from .serializers import (
    ConfirmarImportacionSerializer,
    FilaImportacionSerializer,
    ImportacionSerializer,
    SubirImportacionSerializer,
)


class ImportacionViewSet(DelHogarViewSet):
    """Extractos bancarios: subir (202) → vista previa → confirmar (202) → progreso → completada."""

    modelo = Importacion
    serializer_class = ImportacionSerializer
    http_method_names = ["get", "post", "head", "options"]
    filterset_fields = ["estado", "cuenta"]
    ordering = ["-creado"]
    roles_por_accion = {"deshacer": Membresia.Rol.ADMIN}

    def get_serializer_class(self):
        return {
            "create": SubirImportacionSerializer,
            "confirmar": ConfirmarImportacionSerializer,
            "filas": FilaImportacionSerializer,
        }.get(self.action, ImportacionSerializer)

    def get_throttles(self):
        self.throttle_scope = "subidas" if self.action == "create" else None
        return super().get_throttles()

    def _respuesta(self, importacion, codigo=status.HTTP_200_OK):
        return Response(ImportacionSerializer(importacion).data, status=codigo)

    @extend_schema(responses={202: ImportacionSerializer})
    def create(self, request, *args, **kwargs):
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        with transaction.atomic():
            importacion = services.subir(hogar=self.hogar, usuario=request.user, **entrada.validated_data)
        return self._respuesta(importacion, status.HTTP_202_ACCEPTED)

    @extend_schema(parameters=[OpenApiParameter("accion", enum=FilaImportacion.Accion.values)])
    @action(detail=True, methods=["get"])
    def filas(self, request, *args, **kwargs):
        """La vista previa: cada fila con lo que se hará con ella (?accion=crear|duplicada|conciliar)."""
        filas = FilaImportacion.objects.filter(importacion=self.get_object()).select_related("coincide_con")
        if (accion := request.query_params.get("accion")) in FilaImportacion.Accion.values:
            filas = filas.filter(accion=accion)
        pagina = self.paginate_queryset(filas.order_by("numero"))
        return self.get_paginated_response(self.get_serializer(pagina, many=True).data)

    @extend_schema(request=ConfirmarImportacionSerializer, responses={202: ImportacionSerializer})
    @action(detail=True, methods=["post"])
    def confirmar(self, request, *args, **kwargs):
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        importacion = services.confirmar(self.get_object(), **entrada.validated_data)
        return self._respuesta(importacion, status.HTTP_202_ACCEPTED)

    @extend_schema(request=None, responses={200: ImportacionSerializer})
    @action(detail=True, methods=["post"])
    def deshacer(self, request, *args, **kwargs):
        return self._respuesta(services.deshacer(self.get_object()))
