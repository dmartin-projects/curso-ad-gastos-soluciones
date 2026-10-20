from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import NotificacionViewSet, TicketWebSocketView

router = DefaultRouter()
router.register("notificaciones", NotificacionViewSet, basename="notificacion")

urlpatterns = [
    path("notificaciones/ws-ticket/", TicketWebSocketView.as_view(), name="ws-ticket"),
    *router.urls,
]
