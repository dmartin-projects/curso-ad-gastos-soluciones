from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BajaInformes, InformeViewSet

router = DefaultRouter()
router.register(r"hogares/(?P<hogar_pk>\d+)/informes", InformeViewSet, basename="informe")

urlpatterns = [
    path("informes/baja/<str:token>/", BajaInformes.as_view(), name="informes-baja"),
    *router.urls,
]
