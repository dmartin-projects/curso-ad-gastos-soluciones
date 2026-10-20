from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("hogares", views.HogarViewSet, basename="hogar")
router.register(r"hogares/(?P<hogar_pk>\d+)/miembros", views.MiembrosViewSet, basename="hogar-miembros")
router.register(r"hogares/(?P<hogar_pk>\d+)/invitaciones", views.InvitacionesViewSet, basename="hogar-invitaciones")

urlpatterns = router.urls + [
    path("invitaciones/<str:token>/aceptar/", views.AceptarInvitacion.as_view(), name="invitacion-aceptar"),
]
