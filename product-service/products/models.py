from django.db import models
from django.core.validators import MinValueValidator
from django.utils.text import slugify
import uuid
from django.utils import timezone
from decimal import Decimal

# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< CATEGORY MODEL >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='subcategories')
    slug = models.SlugField(unique=True, blank=True)
    meta_title = models.CharField(max_length=200, blank=True, null=True)
    meta_description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    
    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)
    
    @property
    def subcategories_list(self):
        """Return list of subcategory IDs for Flutter compatibility"""
        return list(self.subcategories.values_list('id', flat=True))


# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< PRODUCT MODEL >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class Product(models.Model):
    PRODUCT_TAGS = [
        ('new', 'New Product'),
        ('on_sale', 'On Sale'),
        ('picked_for_user', 'Picked For User'),
        ('recently_added', 'Recently Added'),
    ]
    
    name = models.CharField(max_length=200)
    description = models.TextField()
    base_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    wholesale_price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True)
   
    
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='products')
    is_active = models.BooleanField(default=True)
    tags = models.JSONField(default=list, blank=True)
    brand = models.CharField(max_length=100, blank=True, null=True)
    origin_country = models.CharField(max_length=100, default='Egypt')
    total_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name
    
    # Helper to access popularity/search weight easily
    @property
    def current_search_weight(self):
        try:
            return self.merchandising.search_weight
        except ProductMerchandising.DoesNotExist:
            return 0
            
    # Helper to access sales count easily
    @property
    def current_sales_count(self):
        try:
            return self.analytics.total_sales_count
        except ProductAnalytics.DoesNotExist:
            return 0
    
    def save(self, *args, **kwargs):
        # Save first to get primary key
        super().save(*args, **kwargs)

        # chek if the product is active 
        self.is_active = self.variants.filter(is_active=True).exists()
        
        # Now calculate and set total_price after saving
        self.total_price = self.calculate_total_price()
        
        # Save again if total_price changed
        if self.total_price != self.base_price:  # Only save again if there was a discount applied
            super().save(update_fields=['total_price'])


    def calculate_total_price(self):
        """Calculate total price after applying active discounts and considering variants"""
        
        # Start with the base price
        total_price = self.base_price
        
        
        # Only try to get discounts if the product has been saved (has a primary key)
        if self.pk:
            # Get active discounts for this product
            active_discounts = self.product_discounts.filter(
                is_active=True,
                start_date__lte=timezone.now(),
                end_date__gte=timezone.now()
            )
            
            # Apply discounts
            for discount in active_discounts:
                if discount.is_valid:
                    discount_amount = (total_price * discount.percentage) / 100
                    total_price -= discount_amount
        
        # Ensure price doesn't go below 0
        return max(total_price, 0)
    
    def get_variant_total_price(self, variant_id=None):
        """Get total price for a specific variant or the cheapest variant"""
        if variant_id:
            try:
                variant = self.variants.get(id=variant_id, is_active=True)
                return variant.calculate_total_price()
            except ProductVariant.DoesNotExist:
                return self.calculate_total_price()
        else:
            # Return the cheapest variant price
            active_variants = self.variants.filter(is_active=True)
            if active_variants.exists():
                cheapest_variant = min(active_variants, key=lambda v: v.calculate_total_price())
                return cheapest_variant.calculate_total_price()
            else:
                return self.calculate_total_price()
    

    def activate(self):
        """Activate the product"""
        self.is_active = True
        self.save(update_fields=['is_active'])
    
    def deactivate(self):
        """Deactivate the product"""
        self.is_active = False
        self.save(update_fields=['is_active'])

    def get_total_price(self):
        variants = self.variants.filter(is_active=True)
        if variants.exists():
            prices = [variant.price for variant in variants if variant.price is not None]
            if prices:
                return float(min(prices))
        return float(self.base_price or Decimal("0"))

    def get_price_range(self):
        price = self.get_total_price()
        if price < 20:
            return "under_20"
        if price < 50:
            return "20_to_50"
        if price < 100:
            return "50_to_100"
        return "over_100"

    def get_search_weight(self):
        merchandising = getattr(self, "merchandising", None)
        return getattr(merchandising, "search_weight", 1)

    def get_popularity_score(self):
        merchandising = getattr(self, "merchandising", None)
        score = getattr(merchandising, "popularity_score", 0)
        return float(score or 0)

    def get_featured_on_homepage(self):
        merchandising = getattr(self, "merchandising", None)
        return bool(getattr(merchandising, "featured_on_homepage", False))

    def get_total_sales_count(self):
        analytics = getattr(self, "analytics", None)
        return getattr(analytics, "total_sales_count", 0)

    def get_category_name(self):
        return self.category.name if self.category else "Uncategorized"

    def get_category_search_boost(self):
        boost = getattr(self.category, "search_boost_factor", 1)
        return float(boost or 1)

    def get_skus(self):
        return [
            sku for sku in
            self.variants.filter(is_active=True).values_list("sku", flat=True)
            if sku
        ]

    def get_all_attributes(self):
        values = set()
        for variant in self.variants.all():
            for attr_value in variant.attribute_values.all():
                if attr_value.value:
                    values.add(attr_value.value)
        return list(values)

    def get_brand_name(self):
        return self.brand or "No Brand"

    def get_tags(self):
        if hasattr(self, "tags") and hasattr(self.tags, "values_list"):
            return list(self.tags.values_list("name", flat=True))
        return [self.get_category_name()] if self.category else []

    def get_image_urls(self):
        urls = []
        for image in self.images.all()[:3]:
            try:
                if image.image:
                    urls.append(image.image.url)
            except ValueError:
                continue
        return urls

    def get_availability(self):
        return self.variants.filter(is_active=True, stock__gt=0).exists()


# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< PRODUCT ATTRIBUTE MODEL >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class ProductAttribute(models.Model):
    """Product attribute model - matches Flutter structure"""
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name


class ProductAttributeValue(models.Model):
    """Product attribute value model - matches Flutter structure"""
    attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE, related_name='values')
    value = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.attribute.name}: {self.value}"


# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< PRODUCT VARIANT MODEL >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class ProductVariant(models.Model):
    """Product variant model - matches Flutter structure"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants', null=True, blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)], null=True, blank=True)
    is_active = models.BooleanField(default=True)
    sku = models.CharField(max_length=50, unique=True, blank=True)
    stock = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    reserved_quantity = models.IntegerField(default=0, validators=[MinValueValidator(0)])
    low_stock_threshold = models.IntegerField(default=5, validators=[MinValueValidator(0)])
    reorder_point = models.IntegerField(default=10, validators=[MinValueValidator(0)])
    max_stock_level = models.IntegerField(default=100, validators=[MinValueValidator(0)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    attribute_values = models.ManyToManyField(ProductAttributeValue, related_name='variants')

    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Variant - {self.sku or 'Default'}"
    
    @property
    def available_quantity(self):
        return self.stock - self.reserved_quantity
    
    @property
    def is_low_stock(self):
        return self.available_quantity <= self.low_stock_threshold
    
    @property
    def is_out_of_stock(self):
        return self.available_quantity <= 0
    
    @property
    def needs_reorder(self):
        return self.available_quantity <= self.reorder_point
    
    @property
    def can_reserve(self):
        return self.available_quantity > 0
   
    def save(self, *args, **kwargs):
        if not self.sku:
            self.sku = f"MKH-{uuid.uuid4().hex[:8].upper()}"
        
        # check if the variant is active 
        self.is_active = self.available_quantity > 0

        super().save(*args, **kwargs)
    
    @property
    def can_be_added_to_cart(self):
        """Check if variant can be added to cart"""
        return self.is_active and self.product.is_active and self.available_quantity > 0
    
    @property
    def only_one_left(self):
        return self.available_quantity == 1
    
    def activate(self):
        """Activate the variant"""
        self.is_active = True
        self.save(update_fields=['is_active'])
    
    def deactivate(self):
        """Deactivate the variant"""
        self.is_active = False
        self.save(update_fields=['is_active'])
    
    def calculate_total_price(self):
        """Calculate total price after applying active discounts.
        variant.price is a full price override; if null, fall back to product.base_price.
        """
        if self.price is not None:
            total_price = self.price
        elif self.product:
            total_price = self.product.base_price or Decimal('0.00')
        else:
            total_price = Decimal('0.00')

        # Apply discounts using Decimal arithmetic
        if self.pk:
            active_discounts = self.variant_discounts.filter(
                is_active=True,
                start_date__lte=timezone.now(),
                end_date__gte=timezone.now()
            )
            for discount in active_discounts:
                if discount.is_valid:
                    discount_percentage = Decimal(str(discount.percentage))  # Convert to Decimal
                    discount_amount = (total_price * discount_percentage) / Decimal('100')
                    total_price -= discount_amount.quantize(Decimal('0.01'))  # Round to 2 decimal places

        return max(total_price, Decimal('0.00'))


# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< PRODUCT IMAGE MODEL >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='images', null=True, blank=True)
    variant = models.ForeignKey(ProductVariant, on_delete=models.SET_NULL, null=True, blank=True, related_name='images')
    image = models.ImageField(upload_to='products/')
    is_primary = models.BooleanField(default=False)
    alt_text = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-is_primary', 'created_at']
    
    def __str__(self):
        if self.variant:
            return f"Image for {self.variant}"
        elif self.product:
            return f"Image for {self.product.name}"
        else:
            return "Image"
    
    def save(self, *args, **kwargs):
        if self.is_primary and self.variant:
            # Set other images as non-primary for this variant
            ProductImage.objects.filter(variant=self.variant, is_primary=True).update(is_primary=False)
        super().save(*args, **kwargs)


# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< PRODUCT DISCOUNT MODEL >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class Discount(models.Model):
    """Product discount model - matches Flutter structure"""
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='product_discounts', null=True, blank=True)
    variant = models.ForeignKey(ProductVariant, on_delete=models.CASCADE, related_name='variant_discounts', null=True, blank=True)
    DISCOUNT_TYPES = [('percentage', 'Percentage'), ('fixed', 'Fixed Amount')]
    discount_type = models.CharField(choices=DISCOUNT_TYPES, default='percentage')
    percentage = models.DecimalField(null=True, max_digits=2, decimal_places=2)   
    value = models.DecimalField(null=True, decimal_places=2, max_digits=4)        
    max_usage_count = models.IntegerField(null=True)   
    usage_count = models.IntegerField(default=0)      
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    code = models.CharField(max_length=50, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Discount - {self.percentage}%"
    
    @property
    def is_valid(self):
        from django.utils import timezone
        now = timezone.now()
        return self.is_active and self.start_date <= now <= self.end_date
    
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        
        # Recalculate total prices for affected products/variants
        self.recalculate_affected_prices()
    
    def recalculate_affected_prices(self):
        """Recalculate total prices for products/variants affected by this discount"""
        if self.product:
            self.product.save()  # This will trigger total_price recalculation
        
        if self.variant:
            self.variant.save()  # This will trigger total_price recalculation


# ---------------------------------------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< Model for Merchandising and Ranking Data >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# ---------------------------------------------------------------------------------------------------------------
class ProductMerchandising(models.Model):
    product = models.OneToOneField(
        'Product', 
        on_delete=models.CASCADE, 
        related_name='merchandising' # Access via product.merchandising
    )
    # Manual Merchandising Boost
    search_weight = models.DecimalField(max_digits=5, decimal_places=2, default=1.00) 
    
    # Computed Ranking Score (updated by management command)
    popularity_score = models.DecimalField(
        max_digits=8, 
        decimal_places=2, 
        default=Decimal('0.00')
    ) 

    # Merchandising Flag
    featured_on_homepage = models.BooleanField(default=False)
    
    # Generic/Flexible Data
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Merchandising for {self.product.name}"
    
    class Meta:
        verbose_name_plural = 'Product Merchandising'
        ordering = ['-popularity_score', '-search_weight']


# ---------------------------------------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< Model for High-Frequency Analytics >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# ---------------------------------------------------------------------------------------------------------------
class ProductAnalytics(models.Model):
    product = models.OneToOneField(
        'Product', 
        on_delete=models.CASCADE, 
        related_name='analytics' # Access via product.analytics
    )
    
    # High-Frequency Metric
    total_views = models.PositiveIntegerField(default=0)
    unique_daily_views = models.PositiveIntegerField(default=0)
    
    # Sales/Recency Metrics
    total_sales_count = models.PositiveIntegerField(default=0)
    conversion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    last_viewed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Analytics for {self.product.name}"
    
    class Meta:
        verbose_name_plural = 'Product Analytics'

