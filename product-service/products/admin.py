from django.contrib import admin
from django.db import transaction
from django.urls import path, reverse
from django.shortcuts import redirect
from django.contrib import messages
from django.utils.html import format_html
from .models import (
    Category, Product, ProductImage, ProductVariant, Discount, 
    ProductAttribute, ProductAttributeValue, ProductMerchandising, ProductAnalytics
)
import logging

logger = logging.getLogger(__name__)

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent', 'is_active', 'created_at']
    list_filter = ['is_active', 'parent']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'base_price', 'total_price', 'is_active', 'get_analytics_link']
    list_filter = ['is_active', 'category', 'brand', 'created_at']
    search_fields = ['name', 'description', 'brand']
    readonly_fields = ['total_price', 'created_at', 'updated_at']
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'category', 'brand', 'origin_country')
        }),
        ('Pricing', {
            'fields': ('base_price', 'wholesale_price', 'total_price')
        }),
        ('Settings', {
            'fields': ('is_active', 'tags')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        })
    )
    
    def get_analytics_link(self, obj):
        if hasattr(obj, 'analytics'):
            return format_html(
                '<a href="/admin/products/productanalytics/{}/change/">View Analytics</a>',
                obj.analytics.id
            )
        return 'No Analytics'
    get_analytics_link.short_description = 'Analytics'

@admin.register(ProductMerchandising)
class ProductMerchandisingAdmin(admin.ModelAdmin):
    list_display = ['product', 'search_weight', 'popularity_score', 'featured_on_homepage']
    list_filter = ['featured_on_homepage']
    search_fields = ['product__name']
    list_editable = ['search_weight', 'featured_on_homepage']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')

@admin.register(ProductAnalytics)
class ProductAnalyticsAdmin(admin.ModelAdmin):
    list_display = ['product', 'total_views', 'unique_daily_views', 'total_sales_count', 'conversion_rate', 'last_viewed_at']
    list_filter = ['last_viewed_at']
    search_fields = ['product__name']
    readonly_fields = ['total_views', 'unique_daily_views', 'last_viewed_at']
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related('product')

@admin.register(ProductAttribute)
class ProductAttributeAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'created_at']
    search_fields = ['name', 'slug']
    prepopulated_fields = {'slug': ('name',)}

@admin.register(ProductAttributeValue)
class ProductAttributeValueAdmin(admin.ModelAdmin):
    list_display = ['attribute', 'value', 'created_at']
    list_filter = ['attribute']
    search_fields = ['value', 'attribute__name']

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ['sku', 'product', 'price', 'get_total_price', 'get_attributes', 'stock', 'is_active']
    search_fields = ['sku', 'product__name', 'attribute_values__value']
    list_filter = ['is_active', 'product', 'attribute_values__attribute']
    filter_horizontal = ['attribute_values']
    readonly_fields = ['get_total_price']

    def get_attributes(self, obj):
        return ", ".join([f"{av.attribute.name}: {av.value}" for av in obj.attribute_values.all()])
    get_attributes.short_description = 'Attributes'

    def get_total_price(self, obj):
        return obj.calculate_total_price()
    get_total_price.short_description = 'Total Price (after discounts)'

    def save_model(self, request, obj, form, change):
        try:
            with transaction.atomic():
                # Generate SKU if not provided
                if not obj.sku:
                    product_prefix = obj.product.name[:3].upper()
                    variant_count = ProductVariant.objects.filter(product=obj.product).count() + 1
                    obj.sku = f"{product_prefix}-{variant_count:03d}"

                super().save_model(request, obj, form, change)

                # Create stock location for new variants
                if not change:
                    # TODO: Integrate with inventory service to create stock location
                    pass

                # Initialize analytics for the parent product
                ProductAnalytics.objects.get_or_create(
                    product=obj.product,
                    defaults={
                        'total_views': 0,
                        'total_sales_count': 0,
                        'conversion_rate': 0.0
                    }
                )

                # Initialize merchandising for the parent product
                ProductMerchandising.objects.get_or_create(
                    product=obj.product,
                    defaults={
                        'search_weight': 1.0,
                        'popularity_score': 0.0,
                        'featured_on_homepage': False
                    }
                )

        except Exception as e:
            logger.error(f"Error saving variant or creating related objects: {str(e)}")
            messages.error(request, f"Error: {str(e)}")
            raise

    fieldsets = (
        (None, {
            'fields': (
                'product',
                'sku',
                'attribute_values',
                'price',
                'get_total_price',
                'stock',
            )
        }),
        ('Stock Settings', {
            'fields': (
                'low_stock_threshold',
                'reorder_point',
                'max_stock_level'
            ),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_active',)
        })
    )

@admin.register(ProductImage)
class ProductImageAdmin(admin.ModelAdmin):
    list_display = ['get_product_name', 'get_variant_sku', 'is_primary', 'created_at']
    list_filter = ['is_primary', 'created_at']
    search_fields = ['product__name', 'variant__sku', 'alt_text']
    
    def get_product_name(self, obj):
        return obj.product.name if obj.product else 'No Product'
    get_product_name.short_description = 'Product'
    
    def get_variant_sku(self, obj):
        return obj.variant.sku if obj.variant else 'No Variant'
    get_variant_sku.short_description = 'Variant SKU'

@admin.register(Discount)
class DiscountAdmin(admin.ModelAdmin):
    list_display = ['get_target', 'percentage', 'start_date', 'end_date', 'is_active', 'is_valid']
    list_filter = ['is_active', 'start_date', 'end_date']
    search_fields = ['product__name', 'variant__sku', 'code']
    date_hierarchy = 'start_date'
    
    def get_target(self, obj):
        if obj.product:
            return f"Product: {obj.product.name}"
        elif obj.variant:
            return f"Variant: {obj.variant.sku}"
        return "No Target"
    get_target.short_description = 'Target'
