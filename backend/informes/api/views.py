from datetime import date

from django.http import FileResponse, Http404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from finanzas.api.views import DelHogarViewSet
from informes import services
from informes.models import InformeMensual
from informes.tasks import generar_informe

from .serializers import GenerarInformeSerializer, InformeEncoladoSerializer, InformeSerializer


class InformeViewSet(DelHogarViewSet):
    """Informes mensuales en PDF: /informes/ · /informes/2026-10/ · /informes/2026-10/pdf/"""

    modelo = InformeMensual
    serializer_class = InformeSerializer
    http_method_names = ["get", "post", "head", "options"]
    pagination_class = None
    lookup_field = "periodo"
    lookup_value_regex = r"\d{4}(-\d{2})?"  # 2026-10 (mensual) o 2026 (anual)

    def get_serializer_class(self):
        return GenerarInformeSerializer if self.action == "create" else InformeSerializer

    def get_object(self):
        periodo = self.kwargs["periodo"]
        try:
            if len(periodo) == 4:
                informe = self.get_queryset().get(tipo=InformeMensual.Tipo.ANUAL, mes=date(int(periodo), 1, 1))
            else:
                anio, mes = map(int, periodo.split("-"))
                informe = self.get_queryset().get(tipo=InformeMensual.Tipo.MENSUAL, mes=date(anio, mes, 1))
        except (ValueError, InformeMensual.DoesNotExist) as e:  # ValueError: mes 13
            raise Http404 from e
        self.check_object_permissions(self.request, informe)
        return informe

    @extend_schema(request=GenerarInformeSerializer, responses={202: InformeEncoladoSerializer})
    def create(self, request, *args, **kwargs):
        """Genera (o regenera) un informe bajo demanda, en segundo plano."""
        entrada = self.get_serializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        mes, tipo = entrada.validated_data["mes"], entrada.validated_data["tipo"]
        generar_informe.delay(self.hogar.pk, mes.isoformat(), request.user.pk, entrada.validated_data["enviar"], tipo)
        periodo = f"{mes:%Y}" if tipo == InformeMensual.Tipo.ANUAL else f"{mes:%Y-%m}"
        return Response({"mes": periodo, "estado": "generando"}, status=status.HTTP_202_ACCEPTED)

    @extend_schema(responses={(200, "application/pdf"): OpenApiResponse(description="El PDF")})
    @action(detail=True, methods=["get"])
    def pdf(self, request, *args, **kwargs):
        informe = self.get_object()
        return FileResponse(  # se envía por trozos, sin cargar el PDF entero en memoria
            informe.archivo.open("rb"),
            as_attachment=True,  # Content-Disposition: attachment; filename="…" (lo lee Angular, módulo 51)
            filename=f"gastos-{informe.hogar.nombre}-{informe.periodo}.pdf",
            content_type="application/pdf",
        )


class BajaInformes(APIView):
    """POST /informes/baja/<token>/: la URL de `List-Unsubscribe` (baja en un clic, RFC 8058).

    Sin sesión: la hace el cliente de correo, o la página de baja del frontend. Solo POST: un GET no
    puede cambiar nada, porque los antivirus y los clientes de correo abren los enlaces para analizarlos.
    """

    authentication_classes = []  # sin sesión ni CSRF: el token firmado ES la autorización
    permission_classes = [AllowAny]
    throttle_scope = "baja"  # por IP: el token no se puede adivinar, pero no hace falta dejar probar

    @extend_schema(request=None, responses={204: None, 400: None})
    def post(self, request, version, token):
        if not services.dar_de_baja(token):
            return Response({"detail": "Enlace no válido."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)
