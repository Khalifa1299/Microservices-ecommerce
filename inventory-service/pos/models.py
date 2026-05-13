from django.db import models
from django.conf import settings

class POSSession(models.Model):
    """Represents a cashier shift/session"""
    cashier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='pos_sessions')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    opening_balance = models.DecimalField(max_digits=10, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    actual_closing_balance = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Session {self.id} - {self.cashier}"

class POSOrder(models.Model):
    """Extension of the main Order model for POS specific details"""
    order_id = models.PositiveIntegerField(unique=True)  
    session = models.ForeignKey(POSSession, on_delete=models.PROTECT, related_name='orders')
    amount_tendered = models.DecimalField(max_digits=10, decimal_places=2)
    change_due = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=50, choices=[
        ('cash', 'Cash'),
        ('card', 'Card'),
        ('split', 'Split Payment')
    ])
    
    def __str__(self):
        return f"POS Order {self.order_id}"
