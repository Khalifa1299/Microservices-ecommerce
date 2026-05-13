from rest_framework import serializers
from .models import Category, Product, ProductImage, ProductVariant, Discount, ProductAttribute, ProductAttributeValue

# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< CATEGORY SERIALIZER >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class CategorySerializer(serializers.ModelSerializer):
    subcategories = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = '__all__'
    
    def get_subcategories(self, obj):
        return obj.subcategories_list

class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = '__all__'
    
    def to_representation(self, instance):
        """Convert to Flutter compatible format"""
        data = super().to_representation(instance)
        return {
            'id': data['id'],
            'image': data['image'],
            'is_primary': data['is_primary'],
            'alt_text': data['alt_text'],
            'created_at': data['created_at'],
        }

# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< PRODUCT ATTRIBUTE VALUE SERIALIZER >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class ProductAttributeValueSerializer(serializers.ModelSerializer):
    attribute = serializers.CharField(source='attribute.name', read_only=True)
    
    class Meta:
        model = ProductAttributeValue
        fields = '__all__'

# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< PRODUCT ATTRIBUTE SERIALIZER >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class ProductAttributeSerializer(serializers.ModelSerializer):
    values = ProductAttributeValueSerializer(many=True, read_only=True)
    
    class Meta:
        model = ProductAttribute
        fields = '__all__'



# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< PRODUCT VARIANT SERIALIZER >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class ProductVariantSerializer(serializers.ModelSerializer):
    images = ProductImageSerializer(many=True, read_only=True)
    attribute_values = ProductAttributeValueSerializer(many=True, read_only=True)
    
    class Meta:
        model = ProductVariant
        fields = '__all__'
    
    def to_representation(self, instance):
        """Convert to Flutter compatible format"""
        data = super().to_representation(instance)
        return {
            'id': data['id'],
            'sku': data['sku'],
            'price': data['price'],
            'stock': data['stock'],
            'attribute_values': data['attribute_values'],
            'images': data['images'],
            'is_active': data['is_active'],
            'reserved_quantity': data['reserved_quantity'],
            'low_stock_threshold': data['low_stock_threshold'],
            'reorder_point': data['reorder_point'],
            'max_stock_level': data['max_stock_level'],
            'total_price': instance.calculate_total_price(),
            'created_at': data['created_at'],
            'updated_at': data['updated_at'],
        }

# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< PRODUCT DISCOUNT SERIALIZER >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class DiscountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Discount
        fields = '__all__'
    
    def to_representation(self, instance):
        """Convert to Flutter compatible format"""
        data = super().to_representation(instance)
        return {
            'id': data['id'],
            'product': data['product'],
            'variant': data['variant'],
            'percentage': data['percentage'],
            'start_date': data['start_date'],
            'end_date': data['end_date'],
            'is_active': data['is_active'],
            'code': data['code'],
            'is_valid': instance.is_valid,
        }

# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< PRODUCT SERIALIZER >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class ProductSerializer(serializers.ModelSerializer):
    category = CategorySerializer(read_only=True)
    variants = ProductVariantSerializer(many=True, read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    discounts = serializers.SerializerMethodField()
    
    class Meta:
        model = Product
        fields = '__all__'
        read_only_fields = ['created_at', 'updated_at']
    
    def get_discounts(self, obj):
        """Get discount IDs for the product"""
        return list(obj.product_discounts.values_list('id', flat=True))
    
    def to_representation(self, instance):
        """Convert to Flutter compatible format"""
        data = super().to_representation(instance)
        return {
            'id': data['id'],
            'name': data['name'],
            'description': data['description'],
            'base_price': data['base_price'],
            'wholesale_price': data['wholesale_price'],
            'category': data['category'],
            'variants': data['variants'],
            'images': data['images'],
            'discounts': data['discounts'],
            'is_active': data['is_active'],
            'tags': data['tags'],
            'brand': data['brand'],
            'origin_country': data['origin_country'],
            'total_price': instance.calculate_total_price(),
            'min_variant_price': instance.get_variant_total_price(),
            'created_at': data['created_at'],
            'updated_at': data['updated_at'],
        } 