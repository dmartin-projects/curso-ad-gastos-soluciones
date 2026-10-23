"""Documentación OpenAPI de las vistas de autenticación (APIView sin serializer_class, módulo 38)."""

from drf_spectacular.utils import extend_schema, extend_schema_view, inline_serializer
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from . import auth, views

Access = inline_serializer("Access", {"access": serializers.CharField()})
NuevaPassword = inline_serializer(
    "NuevaPassword",
    {"uid": serializers.CharField(), "token": serializers.CharField(), "password": serializers.CharField()},
)
Email = inline_serializer("Email", {"email": serializers.EmailField()})
Detalle = inline_serializer("Detalle", {"detail": serializers.CharField()})

extend_schema_view(post=extend_schema(request=TokenObtainPairSerializer, responses=Access))(auth.Login)
extend_schema_view(post=extend_schema(request=None, responses=Access))(auth.Refresh)
extend_schema_view(post=extend_schema(request=None, responses={204: None}))(auth.Logout)
extend_schema_view(post=extend_schema(responses={202: Detalle}))(views.Registro)
extend_schema_view(post=extend_schema(request=NuevaPassword, responses={204: None}))(views.CompletarRegistro)
extend_schema_view(post=extend_schema(request=Email, responses=Detalle))(views.SolicitarRecuperacion)
extend_schema_view(post=extend_schema(request=NuevaPassword, responses={204: None}))(views.ConfirmarRecuperacion)
