import csv

from django.db import transaction
from django.db.models import Count, DecimalField, Sum, Value
from django.db.models.functions import Coalesce
from django.forms.models import model_to_dict
from django.http import StreamingHttpResponse
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import filters, mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.api.paginacion import PaginacionCursor, PaginacionEstandar
from core.auditoria import registrar
from core.hojas_de_calculo import texto_csv
from core.models import RegistroAuditoria
from finanzas import dashboard
from finanzas.models import Categoria, Comercio, Cuenta, Movimiento, Presupuesto
from finanzas.servicios_comercios import reconocer_comercio
from finanzas.signals import movimientos_cambiados
from hogares.models import Membresia
from hogares.permissions import HogarDesdeUrlMixin, RolEnHogar

from .filters import MovimientoFilter
from .serializers import (
    CategoriaSerializer,
    ComercioSerializer,
    CuentaSerializer,
    DashboardSerializer,
    MesQuerySerializer,
    MovimientoSerializer,
    PresupuestoSerializer,
    RecategorizarSerializer,
    ReordenarSerializer,
)


class DelHogarViewSet(HogarDesdeUrlMixin, viewsets.ModelViewSet):
    """Base de los recursos anidados en /hogares/{h}/…: permisos por rol, contexto y hogar automáticos."""

    permission_classes = [IsAuthenticated, RolEnHogar]
    modelo = None

    def get_queryset(self):
        if self.es_esquema():
            return self.modelo.objects.none()
        return self.modelo.objects.filter(hogar=self.hogar)

    def get_serializer_context(self):
        contexto = super().get_serializer_context()
        if not self.es_esquema():
            contexto["hogar"] = self.hogar
        return contexto

    def perform_create(self, serializer):
        serializer.save(hogar=self.hogar)


class CuentaViewSet(DelHogarViewSet):
    modelo = Cuenta
    serializer_class = CuentaSerializer
    pagination_class = None
    roles_por_metodo = {
        "GET": Membresia.Rol.LECTOR,
        "POST": Membresia.Rol.ADMIN,
        "PUT": Membresia.Rol.ADMIN,
        "PATCH": Membresia.Rol.ADMIN,
        "DELETE": Membresia.Rol.ADMIN,
    }

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .annotate(saldo=Coalesce(Sum("movimientos__importe"), Value(0), output_field=DecimalField()))
            .order_by("nombre")
        )


class CategoriaViewSet(DelHogarViewSet):
    modelo = Categoria
    serializer_class = CategoriaSerializer
    pagination_class = None

    @extend_schema(request=ReordenarSerializer, responses={204: None})
    @action(detail=False, methods=["post"])
    def reordenar(self, request, *args, **kwargs):
        datos = ReordenarSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        categorias = {c.pk: c for c in self.get_queryset().filter(pk__in=datos.validated_data["ids"])}
        for orden, pk in enumerate(datos.validated_data["ids"]):
            if pk in categorias:
                categorias[pk].orden = orden
        Categoria.objects.bulk_update(categorias.values(), ["orden"])  # una consulta (módulo 09)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MovimientoViewSet(DelHogarViewSet):
    modelo = Movimiento
    serializer_class = MovimientoSerializer
    filterset_class = MovimientoFilter
    search_fields = ["concepto", "comercio__nombre", "notas"]
    ordering_fields = ["fecha", "importe", "concepto"]
    ordering = ["-fecha", "-id"]
    pagination_class = PaginacionCursor
    roles_por_accion = {"destroy": Membresia.Rol.ADMIN, "recategorizar": Membresia.Rol.MIEMBRO}

    def get_queryset(self):
        qs = super().get_queryset().con_detalle()
        if self.action == "list":
            qs = qs.annotate(num_adjuntos=Count("adjuntos"))
        return qs

    @property
    def paginator(self):
        # El cursor necesita un orden fijo: si el usuario ordena por importe, paginación normal (módulo 37)
        if not hasattr(self, "_paginator"):
            ordenado = self.request.query_params.get("ordering") if hasattr(self, "request") else None
            self._paginator = PaginacionEstandar() if ordenado else PaginacionCursor()
        return self._paginator

    def perform_create(self, serializer):
        mov = serializer.save(hogar=self.hogar, creado_por=self.request.user, comercio=self._comercio(serializer))
        registrar(mov, RegistroAuditoria.Accion.CREAR, self.request.user)

    def perform_update(self, serializer):
        antes = model_to_dict(serializer.instance)
        mov = serializer.save()
        registrar(mov, RegistroAuditoria.Accion.MODIFICAR, self.request.user, antes=antes)

    def perform_destroy(self, instance):
        registrar(instance, RegistroAuditoria.Accion.BORRAR, self.request.user)
        instance.delete()

    def _comercio(self, serializer):
        """Reconoce el comercio por similitud del concepto (índice trigram, módulos 72 y 74)."""
        return reconocer_comercio(serializer.validated_data.get("concepto", ""))

    @extend_schema(
        request=RecategorizarSerializer,
        responses={200: {"type": "object", "properties": {"actualizados": {"type": "integer"}}}},
    )
    @action(detail=False, methods=["post"])
    def recategorizar(self, request, *args, **kwargs):
        datos = RecategorizarSerializer(data=request.data, context=self.get_serializer_context())
        datos.is_valid(raise_exception=True)
        with transaction.atomic():
            seleccion = self.get_queryset().filter(pk__in=datos.validated_data["ids"])
            meses = set(seleccion.dates("fecha", "month"))
            n = seleccion.update(categoria=datos.validated_data["categoria"], revisado=True)
            # update() no emite post_save: se avisa a mano (dashboard y presupuestos, módulos 76 y 77)
            transaction.on_commit(
                lambda: movimientos_cambiados.send(sender=Movimiento, hogar_id=self.hogar.pk, meses=meses)
            )
        return Response({"actualizados": n})

    @extend_schema(responses={(200, "text/csv"): str})
    @action(detail=False, methods=["get"])
    def exportar(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset()).values_list(
            "fecha", "concepto", "importe", "cuenta__nombre", "categoria__nombre", "etiquetas"
        )

        class Eco:
            def write(self, valor):
                return valor

        escritor = csv.writer(Eco(), delimiter=";")
        cabecera = escritor.writerow(["fecha", "concepto", "importe", "cuenta", "categoría", "etiquetas"])
        filas = (
            # el texto (de terceros) sin fórmulas; el importe, tal cual: "-12,50" es un número
            escritor.writerow(
                [f, texto_csv(c), str(i).replace(".", ","), texto_csv(cu), texto_csv(ca or ""), texto_csv(",".join(e))]
            )
            for f, c, i, cu, ca, e in qs.iterator(chunk_size=2000)
        )
        respuesta = StreamingHttpResponse(
            (x for bloque in ([cabecera], filas) for x in bloque), content_type="text/csv; charset=utf-8"
        )
        respuesta["Content-Disposition"] = f'attachment; filename="movimientos-{self.hogar.pk}.csv"'
        return respuesta


class PresupuestoViewSet(DelHogarViewSet):
    modelo = Presupuesto
    serializer_class = PresupuestoSerializer
    pagination_class = None
    roles_por_metodo = {
        "GET": Membresia.Rol.LECTOR,
        "POST": Membresia.Rol.ADMIN,
        "PUT": Membresia.Rol.ADMIN,
        "PATCH": Membresia.Rol.ADMIN,
        "DELETE": Membresia.Rol.ADMIN,
    }

    @extend_schema(parameters=[OpenApiParameter("mes", str, description="Mes en formato AAAA-MM")])
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        qs = super().get_queryset().select_related("categoria")
        if not self.es_esquema() and (mes := self.request.query_params.get("mes")):
            qs = qs.filter(mes=f"{mes}-01")
        return qs.con_gastado().order_by("categoria__orden")  # Subquery correlacionada (módulos 07 y 76)


class ComercioViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Autocompletado de comercios (global): /comercios/?search=merca"""

    queryset = Comercio.objects.order_by("nombre")
    serializer_class = ComercioSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["nombre"]


class DashboardView(HogarDesdeUrlMixin, APIView):
    """Resumen del mes. Cacheado por hogar y versión; responde 304 si el cliente ya tiene la versión actual."""

    permission_classes = [IsAuthenticated, RolEnHogar]  # GET → lector

    @extend_schema(parameters=[MesQuerySerializer], responses={200: DashboardSerializer, 304: None})
    def get(self, request, *args, **kwargs):
        consulta = MesQuerySerializer(data=request.query_params)
        consulta.is_valid(raise_exception=True)
        mes = consulta.validated_data.get("mes") or dashboard.mes_actual(self.hogar)

        # ETag barato: no hace falta calcular nada para saber si el cliente ya lo tiene (módulo 23)
        etag = f'"dashboard-{self.hogar.pk}-v{dashboard.version(self.hogar.pk)}-{mes:%Y-%m}"'
        cabeceras = {"ETag": etag, "Cache-Control": "private, no-cache"}  # el navegador guarda, pero pregunta
        if etag in request.headers.get("If-None-Match", ""):
            return Response(status=status.HTTP_304_NOT_MODIFIED, headers=cabeceras)

        datos, _ = dashboard.obtener(self.hogar, mes)
        return Response(DashboardSerializer(datos).data, headers=cabeceras)
