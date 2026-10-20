from rest_framework.routers import DefaultRouter

from .views import FilaImportacionViewSet, ImportacionViewSet, PerfilBancoViewSet

router = DefaultRouter()
router.register(r"hogares/(?P<hogar_pk>\d+)/importaciones", ImportacionViewSet, basename="importacion")
router.register(
    r"hogares/(?P<hogar_pk>\d+)/importaciones/(?P<importacion_pk>\d+)/filas",
    FilaImportacionViewSet,
    basename="importacion-fila",
)
router.register(r"hogares/(?P<hogar_pk>\d+)/perfiles-banco", PerfilBancoViewSet, basename="perfil-banco")

urlpatterns = router.urls
