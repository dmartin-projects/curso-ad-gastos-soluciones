from django.db.models import Count, OuterRef, Subquery
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from hogares import services
from hogares.models import Hogar, Invitacion, Membresia
from hogares.permissions import HogarDesdeUrlMixin, RolEnHogar

from .serializers import HogarSerializer, InvitacionSerializer, InvitarSerializer, MiembroSerializer


class HogarViewSet(viewsets.ModelViewSet):
    """Mis hogares. Crear lo puede cualquiera; editar y borrar, solo administradores."""

    serializer_class = HogarSerializer

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):
            return Hogar.objects.none()
        mi_rol = Membresia.objects.filter(hogar=OuterRef("pk"), usuario=self.request.user).values("rol")[:1]
        return (
            Hogar.objects.filter(membresias__usuario=self.request.user)
            .annotate(mi_rol=Subquery(mi_rol), num_miembros=Count("membresias", distinct=True))
            .order_by("nombre")
        )

    def perform_create(self, serializer):
        serializer.instance = services.crear_hogar(usuario=self.request.user, **serializer.validated_data)

    def create(self, request, *args, **kwargs):
        respuesta = super().create(request, *args, **kwargs)
        respuesta.data = self.get_serializer(self.get_queryset().get(pk=respuesta.data["id"])).data  # con mi_rol
        return respuesta

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if request.method not in ("GET", "HEAD", "OPTIONS") and obj.mi_rol != Membresia.Rol.ADMIN:
            self.permission_denied(request, message="Solo los administradores pueden modificar el hogar.")


class MiembrosViewSet(
    HogarDesdeUrlMixin,
    mixins.ListModelMixin,
    mixins.UpdateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):
    """/hogares/{h}/miembros/: ver (todos), cambiar rol y expulsar (admin)."""

    serializer_class = MiembroSerializer
    permission_classes = [IsAuthenticated, RolEnHogar]
    roles_por_metodo = {
        "GET": Membresia.Rol.LECTOR,
        "PATCH": Membresia.Rol.ADMIN,
        "PUT": Membresia.Rol.ADMIN,
        "DELETE": Membresia.Rol.LECTOR,  # cualquiera puede salir; expulsar se comprueba en perform_destroy
        "POST": Membresia.Rol.ADMIN,
    }
    pagination_class = None

    def get_queryset(self):
        if self.es_esquema():
            return Membresia.objects.none()
        return Membresia.objects.filter(hogar=self.hogar).select_related("usuario").order_by("creado")

    def perform_update(self, serializer):
        services.cambiar_rol(membresia=serializer.instance, rol=serializer.validated_data["rol"])

    def perform_destroy(self, instance):
        es_uno_mismo = instance.usuario_id == self.request.user.pk
        if not es_uno_mismo and self.membresia.rol != Membresia.Rol.ADMIN:
            self.permission_denied(self.request, message="Solo los administradores pueden expulsar a otros miembros.")
        services.quitar_miembro(membresia=instance)

    @extend_schema(request=InvitarSerializer, responses={201: InvitacionSerializer})
    @action(detail=False, methods=["post"])
    def invitar(self, request, *args, **kwargs):
        datos = InvitarSerializer(data=request.data)
        datos.is_valid(raise_exception=True)
        inv = services.invitar(hogar=self.hogar, invitado_por=request.user, **datos.validated_data)
        return Response(InvitacionSerializer(inv).data, status=status.HTTP_201_CREATED)


class InvitacionesViewSet(HogarDesdeUrlMixin, mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """/hogares/{h}/invitaciones/: ver y anular invitaciones pendientes (solo admin)."""

    serializer_class = InvitacionSerializer
    permission_classes = [IsAuthenticated, RolEnHogar]
    roles_por_metodo = {"GET": Membresia.Rol.ADMIN, "DELETE": Membresia.Rol.ADMIN}
    pagination_class = None

    def get_queryset(self):
        if self.es_esquema():
            return Invitacion.objects.none()
        # Solo pendientes: una invitación aceptada es historia y no se "anula" (para eso, expulsar al miembro).
        return Invitacion.objects.filter(hogar=self.hogar, aceptada__isnull=True).order_by("-creado")


class AceptarInvitacion(APIView):
    @extend_schema(request=None, responses={200: MiembroSerializer})
    def post(self, request, version, token):
        membresia = services.aceptar_invitacion(token=token, usuario=request.user)
        return Response(MiembroSerializer(membresia).data)
