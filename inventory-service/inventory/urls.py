# inventory/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    WarehouseListView, WarehouseDetailView,
    StockLocationListView, StockLocationDetailView,
    StockMovementListView, BatchStockUpdateView
)

app_name = 'inventory'  # Namespace for URL reversing

urlpatterns = [
    path('warehouses/', WarehouseListView.as_view(), name='warehouse-list'),
    path('warehouses/<int:pk>/', WarehouseDetailView.as_view(), name='warehouse-detail'),
    path('stock-locations/', StockLocationListView.as_view(), name='stock-location-list'),
    path('stock-locations/<int:pk>/', StockLocationDetailView.as_view(), name='stock-location-detail'),
    path('stock-movements/', StockMovementListView.as_view(), name='stock-movement-list'),
    path('batch-update/', BatchStockUpdateView.as_view(), name='batch-stock-update'),
]