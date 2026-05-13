from django.urls import path, include
from .views import (
    OrderViewSet,
    OrderCancelView, OrderTrackingView, OrderItemsView
)
from rest_framework.routers import DefaultRouter

app_name = 'orders'
router = DefaultRouter()
router.register(r'orders', OrderViewSet, basename='order')

urlpatterns = [
    # Order URLs

    #path('orders/', OrderViewSet.as_view({'get': 'list', 'post': 'create'}), name='order-list'),
    #path('orders/<int:pk>/', OrderDetailView.as_view(), name='order-detail'),
    #path('orders/<int:pk>/status/', OrderStatusUpdateView.as_view(), name='order-status-update'),
    #path('orders/<int:pk>/cancel/', OrderCancelView.as_view(), name='order-cancel'),
    #path('orders/<int:pk>/tracking/', OrderTrackingView.as_view(), name='order-tracking'),
    #path('orders/<int:order_id>/items/', OrderItemsView.as_view(), name='order-items'),
    
    path('', include(router.urls)),

]