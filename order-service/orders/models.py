from django.db import models
from django.conf import settings
from django.db.models import F, Sum
from django.core.validators import MinValueValidator
from django.db import transaction

class Order(models.Model):
    user_id = models.PositiveIntegerField()  
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('shipped', 'Shipped'),
            ('delivered', 'Delivered'),
            ('cancelled', 'Cancelled'),
        ],
        default='pending'
    )
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash on Delivery'),
        ('card', 'Card / Paymob'),
        ('wallet', 'E-Wallet'),
    ]
    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, default='cash'
    )
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    coupon_code = models.CharField(max_length=50, null=True, blank=True)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    shipping_address = models.TextField(null=True, blank=True)
    billing_address = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # Intentional change if typo
    tracking_number = models.CharField(max_length=100, null=True, blank=True)
    carrier = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"Order #{self.id} -  User #{self.user_id} - {self.status}"

    @property
    def get_total_price(self):
        """Returns the persisted total_amount (subtotal + tax + shipping - discount)."""
        return self.total_amount
    
    def save(self, *args, **kwargs):
        """
        Save method optimized to avoid recursive calls.
        Total_amount is handled by signals or view logic after initial save.
        """
        is_new = not self.pk
        super().save(*args, **kwargs)  # Initial save to ensure PK
        

class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    variant_id = models.PositiveIntegerField()
    product_id = models.PositiveIntegerField()
    quantity = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)  
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.quantity} x Variant #{self.variant_id} for Order #{self.order.id}"

    def get_total_price(self):
        """
        Calculates the total price for this item, handling None values.
        """
        if self.unit_price is None:
            return 0.00
        if self.quantity is None:
            return 0.00
        return float(self.unit_price) * self.quantity

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)