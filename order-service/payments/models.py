# payments/models.py
from django.db import models
from django.conf import settings
from django.utils import timezone
from orders.models import Order
from django.core.validators import MinValueValidator
from cryptography.fernet import Fernet
from django.conf import settings

# Encryption helper for card numbers
class CardEncryption:
    @staticmethod
    def encrypt_card_number(card_number):
        """Encrypt card number and return last 4 digits"""
        # Store only last 4 digits for display
        return card_number[-4:]
    
    @staticmethod
    def mask_card_number(last_four):
        """Return masked card number"""
        return f"****-****-****-{last_four}"

class PaymentMethod(models.Model):
    """User's saved payment methods (credit/debit cards)"""
    CARD_TYPE_CHOICES = [
        ('visa', 'Visa'),
        ('mastercard', 'Mastercard'),
        ('amex', 'American Express'),
        ('discover', 'Discover'),
    ]
    
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payment_methods')
    cardholder_name = models.CharField(max_length=100)
    # Store only last 4 digits for security - actual card stored in payment gateway
    card_number = models.CharField(max_length=4, help_text="Last 4 digits only")
    expiry_month = models.CharField(max_length=2)
    expiry_year = models.CharField(max_length=2, help_text="Last 2 digits of year")
    card_type = models.CharField(max_length=20, choices=CARD_TYPE_CHOICES, default='visa')
    is_default = models.BooleanField(default=False)
    
    # Optional billing address (if different from shipping)
    billing_address_id = models.CharField(max_length=255, blank=True, null=True)
    
    # Payment gateway token (Stripe customer ID, PayPal token, etc.)
    gateway_token = models.CharField(max_length=255, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-is_default', '-created_at']
        indexes = [
            models.Index(fields=['user', 'is_default']),
        ]
    
    def __str__(self):
        return f"{self.cardholder_name} - {self.card_type} ****{self.card_number}"
    
    @property
    def masked_card_number(self):
        return CardEncryption.mask_card_number(self.card_number)
    
    @property
    def expiry_date(self):
        return f"{self.expiry_month}/{self.expiry_year}"
    
    def is_expired(self):
        """Check if card is expired"""
        from datetime import datetime
        try:
            expiry = datetime(int(f"20{self.expiry_year}"), int(self.expiry_month), 1)
            return expiry < datetime.now()
        except (ValueError, TypeError):
            return True
    
    def save(self, *args, **kwargs):
        # Ensure only one default payment method per user
        if self.is_default:
            PaymentMethod.objects.filter(user=self.user, is_default=True).update(is_default=False)
        super().save(*args, **kwargs)

class PaymentTransaction(models.Model):
    """Payment transactions for orders"""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='transactions')
    payment_method = models.ForeignKey(PaymentMethod, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
            ('refunded', 'Refunded'),
        ],
        default='pending'
    )
    provider = models.CharField(
        max_length=50,
        choices=[('paymob', 'Paymob'), ('stripe', 'Stripe'), ('paypal', 'PayPal')],
        default='paymob',
    )
    transaction_id = models.CharField(max_length=100, unique=True, blank=True, null=True)
    # Paymob-specific fields
    paymob_order_id = models.CharField(max_length=100, blank=True, null=True)
    payment_key     = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Transaction #{self.id} for Order #{self.order.id} - {self.status}"

class Refund(models.Model):
    """Refund records for transactions"""
    transaction = models.ForeignKey(PaymentTransaction, on_delete=models.CASCADE, related_name='refunds')
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    reason = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('processed', 'Processed'),
            ('failed', 'Failed'),
        ],
        default='pending'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Refund #{self.id} for Transaction #{self.transaction.id}"