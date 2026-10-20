from datetime import date

from django.http import FileResponse, Http404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from finanzas.api.views import DelHogarViewSet
from informes.models import InformeMensual
from informes.tasks import generar_informe

from .serializers import GenerarInformeSerializer, InformeEncoladoSerializer, InformeSerializer


class InformeViewSet(DelHogarViewSet):
    """Informes mensuales en PDF: /informes/ · /informes/2026-10/ · /informes/2026-10/pdf/"""

    modelo = InformeMensual
    serializer_class = InformeSerializer
    http_method_names = ["get", "post", "head", "options"]
    pagination_class = None
    lookup_field = "mes"
    lookup_value_regex = r"\d{4}-\d{2}"

    def get_serializer_class(self):
        return GenerarInformeSerializer if self.action == "create" else InformeSerializer

    def get_object(self):
        anio, mes = map(int, self.kwargs["mes"].split("-"))
        try:
            informe = self.get_queryset().get(mes=date(anio, mes, 1))
        except (ValueError, InformeMensual.DoesNotExist) as e:  # ValueError: mes 13
            raise Http404 from e
        self.check_object_permissions(self.request, informe)
        return informe

    @extend_schema(request=GenerarInformeSerializer, responses={202: InformeEncoladoSerializer})
    def create(self, request, *args, **kwargs):
        """Genera (o regenera) un informe bajo demanda, en segundo plano."""
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        mes = entrada.validated_data["mes"]
        generar_informe.delay(self.hogar.pk, mes.isoformat(), request.user.pk, entrada.validated_data["enviar"])
        return Response({"mes": f"{mes:%Y-%m}", "estado": "generando"}, status=status.HTTP_202_ACCEPTED)

    @extend_schema(responses={(200, "application/pdf"): OpenApiResponse(description="El PDF")})
    @action(detail=True, methods=["get"])
    def pdf(self, request, *args, **kwargs):
        informe = self.get_object()
        return FileResponse(  # se envía por trozos, sin cargar el PDF entero en memoria
            informe.archivo.open("rb"),
            as_attachment=True,  # Content-Disposition: attachment; filename="…" (lo lee Angular, módulo 51)
            filename=f"gastos-{informe.hogar.nombre}-{informe.mes:%Y-%m}.pdf",
            content_type="application/pdf",
        )
