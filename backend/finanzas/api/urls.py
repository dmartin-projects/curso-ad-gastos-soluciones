from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
H = r"hogares/(?P<hogar_pk>\d+)"
router.register(f"{H}/cuentas", views.CuentaViewSet, basename="cuenta")
router.register(f"{H}/categorias", views.CategoriaViewSet, basename="categoria")
router.register(f"{H}/movimientos", views.MovimientoViewSet, basename="movimiento")
router.register(f"{H}/presupuestos", views.PresupuestoViewSet, basename="presupuesto")
router.register("comercios", views.ComercioViewSet, basename="comercio")

urlpatterns = router.urls + [
    path("hogares/<int:hogar_pk>/dashboard/", views.DashboardView.as_view(), name="dashboard"),
]
