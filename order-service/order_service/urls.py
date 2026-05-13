from django.urls import path, include

urlpatterns = [
    path('', include('django_prometheus.urls')),
    path('api/orders/',   include('orders.urls')),
    path('api/payments/', include('payments.urls')),
    path('api/shipping/', include('shipping.urls')),
]
