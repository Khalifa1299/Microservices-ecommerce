# apps/shipping/serializers.py
from rest_framework import serializers
from .models import Shipment, TrackingEvent
from orders.models import Order

class TrackingEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackingEvent
        fields = ['event_type', 'event_description', 'location', 'event_time']

class ShipmentSerializer(serializers.ModelSerializer):
    tracking_events = TrackingEventSerializer(many=True, read_only=True)
    
    class Meta:
        model = Shipment
        fields = '__all__'
        read_only_fields = ['id', 'tracking_number', 'label_url', 'created_at', 'updated_at']

class CreateShipmentSerializer(serializers.Serializer):
    order_id = serializers.PrimaryKeyRelatedField(queryset=Order.objects.all())
    carrier = serializers.ChoiceField(choices=Shipment.Carrier.choices)
    service_type = serializers.CharField(max_length=100)
    
    destination_address = serializers.CharField()
    
    weight = serializers.DecimalField(max_digits=8, decimal_places=2)
    length = serializers.DecimalField(max_digits=6, decimal_places=2)
    width = serializers.DecimalField(max_digits=6, decimal_places=2)
    height = serializers.DecimalField(max_digits=6, decimal_places=2)
    package_type = serializers.CharField(max_length=50, default='package')

class RateRequestSerializer(serializers.Serializer):
    destination_address = serializers.CharField()
    weight = serializers.DecimalField(max_digits=8, decimal_places=2)
    length = serializers.DecimalField(max_digits=6, decimal_places=2)
    width = serializers.DecimalField(max_digits=6, decimal_places=2)
    height = serializers.DecimalField(max_digits=6, decimal_places=2)
    package_type = serializers.CharField(max_length=50, default='package')

class ShippingRateSerializer(serializers.Serializer):
    carrier = serializers.CharField()
    rate = serializers.ListField(child=serializers.DecimalField(max_digits=10, decimal_places=2))
    transit_days = serializers.IntegerField()
    delivery_date = serializers.DateField(allow_null=True)
