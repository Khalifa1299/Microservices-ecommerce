# inventory/models.py
from django.conf import settings
from django.db import models
from django.db.models import F
from django.utils import timezone
from django.core.validators import MinValueValidator
from django.db import transaction

class Warehouse(models.Model):
    name = models.CharField(max_length=100, unique=True)
    location = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class StockLocation(models.Model):
    variant_id = models.PositiveIntegerField()
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stock_locations')
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    reserved_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    low_stock_threshold = models.IntegerField(default=5, validators=[MinValueValidator(0)])
    reorder_point = models.IntegerField(default=10, validators=[MinValueValidator(0)])
    max_stock_level = models.IntegerField(default=100, validators=[MinValueValidator(0)])

    class Meta:
        unique_together = ('variant_id', 'warehouse')

    def __str__(self):
        return f"Variant {self.variant_id} at {self.warehouse}"

    @property
    def available_quantity(self):
        return self.stock - self.reserved_quantity

    @property
    def is_out_of_stock(self):
        return self.available_quantity <= 0

    @property
    def needs_reorder(self):
        return self.available_quantity <= self.reorder_point

    def reserve_stock(self, quantity):
        if quantity > self.available_quantity:
            raise ValueError("Insufficient stock to reserve")
        with transaction.atomic():
            self = StockLocation.objects.select_for_update().get(pk=self.pk)
            self.reserved_quantity = F('reserved_quantity') + quantity
            self.save(update_fields=['reserved_quantity'])
            self._log_movement(-quantity, 'reserve')  # Negative for reservation

    def release_stock(self, quantity):
        with transaction.atomic():
            self = StockLocation.objects.select_for_update().get(pk=self.pk)
            if quantity > self.reserved_quantity:
                raise ValueError("Cannot release more than reserved")
            self.reserved_quantity = F('reserved_quantity') - quantity
            self.save(update_fields=['reserved_quantity'])
            self._log_movement(quantity, 'release')  # Positive for release

    def adjust_stock(self, quantity, reason='adjustment'):
        with transaction.atomic():
            self = StockLocation.objects.select_for_update().get(pk=self.pk)
            self.stock = F('stock') + quantity
            self.save(update_fields=['stock'])
            self._log_movement(quantity, reason)

    def _log_movement(self, quantity, movement_type):
        StockMovement.objects.create(
            stock_location=self,
            quantity=quantity,
            movement_type=movement_type,
            notes=f"Automated {movement_type} for {quantity} units"
        )

class StockMovement(models.Model):
    MOVEMENT_TYPES = [
        ('in', 'Stock In'),
        ('out', 'Stock Out'),
        ('reserve', 'Reservation'),
        ('release', 'Release'),
        ('adjustment', 'Adjustment'),
    ]

    stock_location = models.ForeignKey(StockLocation, on_delete=models.CASCADE, related_name='movements')
    quantity = models.IntegerField()  # Positive for in/release, negative for out/reserve
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    user_id = models.PositiveIntegerField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.movement_type} of {self.quantity} for {self.stock_location}"