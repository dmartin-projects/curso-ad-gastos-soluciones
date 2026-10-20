from rest_framework.routers import DefaultRouter

from .views import TicketViewSet

router = DefaultRouter()
router.register(r"hogares/(?P<hogar_pk>\d+)/tickets", TicketViewSet, basename="ticket")

urlpatterns = router.urls
