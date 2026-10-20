from rest_framework.routers import DefaultRouter

from .views import ImportacionViewSet

router = DefaultRouter()
router.register(r"hogares/(?P<hogar_pk>\d+)/importaciones", ImportacionViewSet, basename="importacion")

urlpatterns = router.urls
