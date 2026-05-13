# shipping/urls.py
from rest_framework.routers import DefaultRouter
from .views import ShipmentViewSet

app_name = 'shipping'

router = DefaultRouter()
router.register(r'shipments', ShipmentViewSet, basename='shipment')
urlpatterns = router.urls