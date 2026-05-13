# shipping/admin.py
from django.contrib import admin
from .models import Shipment, ShippingRate, TrackingEvent

admin.site.register(Shipment)
admin.site.register(ShippingRate)
admin.site.register(TrackingEvent)