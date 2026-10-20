from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("tickets", views.TicketSoporteViewSet, basename="soporte-ticket")
router.register("importaciones", views.ImportacionSoporteViewSet, basename="soporte-importacion")
router.register("hogares", views.HogarSoporteViewSet, basename="soporte-hogar")
router.register("usuarios", views.UsuarioSoporteViewSet, basename="soporte-usuario")
router.register("movimientos", views.MovimientoSoporteViewSet, basename="soporte-movimiento")
router.register("comercios", views.ComercioSoporteViewSet, basename="soporte-comercio")
router.register("auditoria", views.AuditoriaViewSet, basename="soporte-auditoria")
router.register("tareas", views.TareaProgramadaViewSet, basename="soporte-tarea")

urlpatterns = [path("resumen/", views.ResumenView.as_view(), name="soporte-resumen"), *router.urls]
