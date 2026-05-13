from django.urls import path, include
from rest_framework.routers import DefaultRouter

router = DefaultRouter()
# Add your POS viewsets here when you create them
# router.register(r'sales', SaleViewSet, basename='sales')

app_name = 'pos'

urlpatterns = [
    path('', include(router.urls)),
]