from rest_framework.routers import DefaultRouter

from .views import InformeViewSet

router = DefaultRouter()
router.register(r"hogares/(?P<hogar_pk>\d+)/informes", InformeViewSet, basename="informe")

urlpatterns = router.urls
