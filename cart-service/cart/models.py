from decimal import Decimal
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils import timezone


# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< Copoun MODEL >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class Coupon(models.Model):
    """Coupon model for discount codes"""
    code = models.CharField(max_length=50, unique=True)
    description = models.TextField(null=True, blank=True)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(100)], null=True, blank=True)
    value = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True)
    active = models.BooleanField(default=True)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Coupon {self.code} - {self.discount_percentage}%"
    
    def is_valid(self):
        now = timezone.now()
        return self.active and self.valid_from <= now <= self.valid_to
    
# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< CART MODEL >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class Cart(models.Model):
    """Shopping cart model - matches Flutter structure"""
    user_id = models.PositiveIntegerField()  
    coupon = models.ForeignKey('Coupon', on_delete=models.SET_NULL, null=True, blank=True, related_name='carts')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Cart for User {self.user_id}"
    
    @property
    def discounted_total(self):
        """
        Calculates the total amount after applying a valid coupon.
        """
        total = self.total_amount
        if self.coupon and self.coupon.is_valid():
            if self.coupon.discount_percentage:
                discount = (self.coupon.discount_percentage / 100) * total
                total -= discount
            elif self.coupon.value:
                total -= self.coupon.value
            
        
        return max(0, total) # Ensure total is not negative

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        
        # Only calculate total if cart has been saved (has pk)
        if self.pk:
            self.total_amount = sum(item.subtotal for item in self.cart_items.all())
        else:
            # For new carts, set default total
            self.total_amount = 0
           
        super().save(*args, **kwargs)


class CartItem(models.Model):
    """Cart item model - matches Flutter structure"""
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='cart_items')
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True)
    variant_id = models.PositiveIntegerField()  
    quantity = models.IntegerField(validators=[MinValueValidator(0.01)], default=1)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True)
    image_id = models.PositiveBigIntegerField(null=True, blank=True)  
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['variant_id', 'cart']
        ordering = ['-added_at']
    
    def __str__(self):
        variant_id = str(self.variant_id) if self.variant_id else "Unknown variant"
        return f"Variant {variant_id} in Cart for User {self.user_id}"
    
    def save(self, *args, **kwargs):
        self.subtotal = (self.unit_price or Decimal('0.00')) * self.quantity
        super().save(*args, **kwargs)
    

    @property
    def user_id(self):
        """Get user ID for Flutter compatibility"""
        return self.cart.user_id

# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< WISHLIST MODEL >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class Wishlist(models.Model):
    """Wishlist model - matches Flutter structure"""
    user_id = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Wishlist for User {self.user_id}"
    

# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< WISHLIST ITEM MODEL >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class WishlistItem(models.Model):
    """Wishlist item model - matches Flutter structure"""
    wishlist = models.ForeignKey(Wishlist, on_delete=models.CASCADE, related_name='wishlist_items', default=None)
    user_id = models.PositiveIntegerField()
    product_id = models.PositiveIntegerField()
    variant_id = models.PositiveIntegerField(null=True, blank=True)
    image_id = models.PositiveBigIntegerField(null=True, blank=True)
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['user_id', 'product_id']
        ordering = ['-added_at']
    
    def __str__(self):
        return f"Product {self.product_id} in Wishlist for User {self.user_id}"


