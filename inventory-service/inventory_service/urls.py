from django.urls import path, include

urlpatterns = [
    path('', include('django_prometheus.urls')),
    path('api/inventory/', include('inventory.urls')),
    path('api/analytics/', include('analytics.urls')),
    path('api/pos/',       include('pos.urls')),
]
