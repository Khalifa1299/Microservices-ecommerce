from algoliasearch_django import AlgoliaIndex
from algoliasearch_django.decorators import register
from django.db.models import Prefetch
from decimal import Decimal
from django.conf import settings as django_settings

from .models import Product, Category, ProductVariant


@register(Product)
class ProductIndex(AlgoliaIndex):
    index_name = f"{django_settings.ALGOLIA.get('INDEX_PREFIX', '')}products"
    algolia_settings = {
        "searchableAttributes": [
            "unordered(name)",
            "brand",
            "description",
            "get_category_name",
            "get_all_attributes",
            "get_skus",
        ],
        "customRanking": [
            "desc(get_search_weight)",
            "desc(get_category_search_boost)",
            "desc(get_popularity_score)",
            "desc(get_total_sales_count)",
            "desc(get_availability)",
            "asc(get_total_price)",
        ],
        "attributesForFaceting": [
            "searchable(get_category_name)",
            "searchable(get_brand_name)",
            "get_price_range",
            "is_active",
            "get_featured_on_homepage",
            "get_availability",
        ],
        "attributesToRetrieve": [
            "name",
            "description",
            "get_total_price",
            "get_category_name",
            "get_brand_name",
            "get_image_urls",
            "get_skus",
            "get_availability",
        ],
        "numericAttributesForFiltering": [
            "get_total_price",
            "get_popularity_score",
        ],
    }

    def get_queryset(self):
        return (
            Product.objects.all()
            .select_related("category")
            .prefetch_related(
                Prefetch(
                    "variants",
                    queryset=ProductVariant.objects.filter(is_active=True)
                    .prefetch_related("attribute_values__attribute"),
                )
            )
        )

    # --- Core Product Fields ---
    def get_total_price(self, obj):
        """Calculate total price including base price and variant prices."""
        variants = obj.variants.filter(is_active=True)
        if variants.exists():
            return float(min(variant.price for variant in variants))
        return float(obj.base_price)

    def get_price_range(self, obj):
        """Get price range for faceting."""
        total_price = self.get_total_price(obj)
        if total_price < 20:
            return "under_20"
        elif total_price < 50:
            return "20_to_50"
        elif total_price < 100:
            return "50_to_100"
        else:
            return "over_100"

    # --- Merchandising Fields (with fallbacks) ---
    def get_search_weight(self, obj):
        """Access the manual boost factor."""
        try:
            return obj.merchandising.search_weight if hasattr(obj, 'merchandising') else 1
        except:
            return 1

    def get_popularity_score(self, obj):
        """Access the computed popularity score."""
        try:
            if hasattr(obj, 'merchandising'):
                return float(obj.merchandising.popularity_score)
            return 0.0
        except:
            return 0.0

    def get_featured_on_homepage(self, obj):
        """Access the merchandising flag."""
        try:
            return obj.merchandising.featured_on_homepage if hasattr(obj, 'merchandising') else False
        except:
            return False
            
    # --- Analytics Fields (with fallbacks) ---
    def get_total_sales_count(self, obj):
        """Access the sales metric."""
        try:
            return obj.analytics.total_sales_count if hasattr(obj, 'analytics') else 0
        except:
            return 0
            
    # --- Category Fields ---
    def get_category_name(self, obj):
        """Access the category name for faceting."""
        return obj.category.name if obj.category else "Uncategorized"
        
    def get_category_search_boost(self, obj):
        """Access the category's search boost factor."""
        try:
            if obj.category and hasattr(obj.category, 'search_boost_factor'):
                return float(obj.category.search_boost_factor)
            return 1.0
        except:
            return 1.0
    
    # --- Variant Data ---
    def get_skus(self, obj):
        """Get a list of all active variant SKUs."""
        return [variant.sku for variant in obj.variants.all() if variant.sku]
    
    def get_all_attributes(self, obj):
        """Get a flat list of all attribute values for better text search."""
        attributes = set()
        for variant in obj.variants.all():
            for attr_value in variant.attribute_values.all():
                if attr_value.value:
                    attributes.add(attr_value.value)
        return list(attributes)

    def get_brand_name(self, obj):
        """Get brand name with fallback."""
        return obj.brand if obj.brand else "No Brand"

    def get_tags(self, obj):
        """Get product tags - fallback to category if no tags field exists."""
        if hasattr(obj, 'tags'):
            return obj.tags
        return [obj.category.name] if obj.category else []

    def get_image_urls(self, obj):
        """Get product image URLs."""
        try:
            return [img.image.url for img in obj.images.all()[:3]]  # Limit to 3 images
        except:
            return []

    def get_availability(self, obj):
        """Check if product has stock."""
        return any(variant.stock > 0 for variant in obj.variants.all())

    # Define the fields to be indexed
    fields = (
        'name',
        'description',
        'base_price',
        'is_active',
        
        # Computed fields
        'get_total_price',
        'get_price_range',
        'get_brand_name',
        'get_tags',
        'get_image_urls',
        'get_availability',
        
        # Merchandising fields
        'get_search_weight',            
        'get_popularity_score',         
        'get_featured_on_homepage',     
        
        # Analytics fields
        'get_total_sales_count',        
        
        # Category fields
        'get_category_name',
        'get_category_search_boost',    
        
        # Variant fields
        'get_skus',                     
        'get_all_attributes',
    )

    # Configure Algolia Index Settings
    settings = {
        'searchableAttributes': [
            'unordered(name)',      
            'get_brand_name',
            'description',
            'get_all_attributes',
            'get_skus',
        ],

        'customRanking': [
            'desc(get_search_weight)', 
            'desc(get_category_search_boost)',
            'desc(get_popularity_score)',
            'desc(get_total_sales_count)', 
            'desc(get_availability)',  # In-stock products rank higher
            'asc(get_total_price)',     # Cheaper products rank higher
        ],
        
        'attributesForFaceting': [
            'searchable(get_category_name)',
            'searchable(get_brand_name)',
            'get_price_range',
            'is_active',
            'get_featured_on_homepage',
            'get_availability',
        ],
        
        'attributesToRetrieve': [
            'name',
            'description', 
            'get_total_price',
            'get_category_name',
            'get_brand_name',
            'get_image_urls',
            'get_skus',
            'get_availability',
        ],
        
        'numericAttributesForFiltering': [
            'get_total_price',
            'get_popularity_score',
        ]
    }