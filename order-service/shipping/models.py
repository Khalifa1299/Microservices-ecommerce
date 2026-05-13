# apps/shipping/models.py
from django.db import models
from orders.models import Order
import uuid


class Shipment(models.Model):
    class Carrier(models.TextChoices):
        ARAMEX = 'aramex', 'Aramex'
        BOSTA = 'bosta', 'Bosta'
        MKH = 'mkh', 'Mostafa Khalifa Shipping'
    
    class Status(models.TextChoices):
        CREATED = 'created', 'Created'
        LABEL_CREATED = 'label_created', 'Label Created'
        IN_TRANSIT = 'in_transit', 'In Transit'
        OUT_FOR_DELIVERY = 'out_for_delivery', 'Out for Delivery'
        DELIVERED = 'delivered', 'Delivered'
        RETURNED = 'returned', 'Returned'
        CANCELLED = 'cancelled', 'Cancelled'
    
    class WeightUnit(models.TextChoices):
        OUNCE = 'oz', 'Ounces'
        GRAM = 'g', 'Grams'
        KILO = 'kg', 'Kilograms'
        
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    carrier = models.CharField(max_length=20, choices=Carrier.choices)
    service_type = models.CharField(max_length=100)
    tracking_number = models.CharField(max_length=100, unique=True, null=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    
    # Addresses as a snapshot (Static - stays the same forever)
    destination_address = models.TextField(
        null=True, 
        blank=True, 
        help_text="Snapshot of the destination address at the time of shipment creation"
    )
    
    # Package information
    weight = models.DecimalField(max_digits=8, decimal_places=2)
    weight_unit = models.CharField(max_length=10, choices=WeightUnit.choices, default=WeightUnit.GRAM)
    length = models.DecimalField(max_digits=6, decimal_places=2)
    width = models.DecimalField(max_digits=6, decimal_places=2)
    height = models.DecimalField(max_digits=6, decimal_places=2)
    package_type = models.CharField(max_length=50, default='package')
    
    # Cost and delivery
    shipping_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    estimated_delivery = models.DateField(null=True)
    actual_delivery = models.DateTimeField(null=True)
    
    # Files and metadata
    label_url = models.URLField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['order']),
            models.Index(fields=['tracking_number']),
            models.Index(fields=['carrier', 'status']),
            models.Index(fields=['created_at']),
        ]

class ShippingRate(models.Model):
    """Cache for shipping rates"""
    origin_zip = models.CharField(max_length=10)
    destination_zip = models.CharField(max_length=10)
    weight = models.DecimalField(max_digits=8, decimal_places=2)
    dimensions_hash = models.CharField(max_length=64)
    carrier = models.CharField(max_length=20, choices=Shipment.Carrier.choices)
    service_type = models.CharField(max_length=100)
    rate = models.DecimalField(max_digits=8, decimal_places=2)
    transit_days = models.IntegerField()
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['origin_zip', 'destination_zip', 'weight']),
            models.Index(fields=['expires_at']),
        ]

class TrackingEvent(models.Model):
    shipment = models.ForeignKey(
        Shipment, 
        on_delete=models.CASCADE, 
        related_name='tracking_events'
    )
    event_type = models.CharField(max_length=100)
    event_description = models.TextField()
    location = models.CharField(max_length=200, blank=True)
    event_time = models.DateTimeField()
    carrier_event_id = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-event_time']
        indexes = [
            models.Index(fields=['shipment', 'event_time']),
        ]
