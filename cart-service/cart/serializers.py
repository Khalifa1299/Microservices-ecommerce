from rest_framework import serializers
from .models import Cart, CartItem, Wishlist, WishlistItem, Coupon

# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< CART ITEM SERIALIZER >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class CartItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(write_only=True, required=False)  # For writing product ID
    variant_id = serializers.IntegerField(write_only=True, required=False)  # For writing variant ID
    image_id = serializers.IntegerField(write_only=True, required=False)  # For writing image ID
    
    class Meta:
        model = CartItem
        fields = [
            'id', 'product_id', 'variant_id', 'variant', 'quantity',
            'added_at', 'subtotal', 'selected_image', 'selected_image_id'
        ]
        read_only_fields = ['subtotal', 'added_at']
    
    def create(self, validated_data):
        # product_id is informational only — CartItem has no product field,
        # product is accessed via variant.product
        validated_data.pop('product_id', None)

        # Handle variant field mapping
        if 'variant_id' in validated_data:
            pass

        # Handle selected_image field mapping
        image_id = validated_data.pop('image_id', None)
        if image_id:
            pass

        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        # Handle variant changes
        if 'variant_id' in validated_data:
            variant_id = validated_data.pop('variant_id')
            if variant_id is not None:
                pass
        
        # Handle quantity updates
        if 'quantity' in validated_data:
            instance.quantity = validated_data['quantity']

        # subtotal is recalculated automatically in CartItem.save()
        return super().update(instance, validated_data)
    
    def to_representation(self, instance):
        """Convert to Flutter compatible format"""
        data = super().to_representation(instance)

        return {
            'id': data['id'],
            'user': instance.cart.user_id,
            'product_id': instance.variant.product_id if instance.variant else None,
            'variant': data['variant'],
            'quantity': data['quantity'],
            'added_at': data['added_at'],
            'subtotal': data['subtotal'],
            'selected_image': data['selected_image'],
        }

# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< COUPON SERIALIZER >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class CouponSerializer(serializers.ModelSerializer):
    """Serializer for the Coupon model"""
    
    class Meta:
        model = Coupon
        fields = [
            'id', 'code', 'description', 'discount_percentage', 'value',
            'active', 'valid_from', 'valid_to', 'created_at', 'updated_at'
        ]
        read_only_fields = ['created_at', 'updated_at']
    
    def to_representation(self, instance):
        """Convert to Flutter compatible format"""
        data = super().to_representation(instance)
        # Add a calculated field to indicate if the coupon is currently valid
        data['is_valid'] = instance.is_valid()
        return data

# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< CART SERIALIZER >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class CartSerializer(serializers.ModelSerializer):
    items = CartItemSerializer(many=True, read_only=True, source='cart_items')
    coupon = CouponSerializer(read_only=True)
    total_amount = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    discounted_total = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = Cart
        fields = ['id', 'user', 'items', 'coupon', 'total_amount', 'discounted_total', 'created_at', 'updated_at']
        read_only_fields = ['total_amount', 'discounted_total', 'created_at', 'updated_at']
    
    def to_representation(self, instance):
        """Convert to Flutter compatible format"""
        data = super().to_representation(instance)
        return {
            'id': data['id'],
            'user': data['user'],
            'items': data['items'],
            'coupon': data['coupon'],
            'total_amount': data['total_amount'],
            'discounted_total': data['discounted_total'],
            'created_at': data['created_at'],
            'updated_at': data['updated_at'],
        }

# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< WISHLIST ITEM SERIALIZER >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class WishlistItemSerializer(serializers.ModelSerializer):
    product_id = serializers.IntegerField(required=True)  # Make product_id required
    variant_id = serializers.IntegerField(required=False, allow_null=True)
    
    class Meta:
        model = WishlistItem
        fields = [
            'id', 
            'user', 
            'product_id',
            'variant_id', 
            'added_at'
        ]
        read_only_fields = ['user', 'added_at']
    
    def create(self, validated_data):
                   
        # Handle variant if provided
        variant_id = validated_data.get('variant_id')
        if variant_id:
            pass
        
        # Create wishlist item
        return super().create(validated_data)
    
    def to_representation(self, instance):
        """Convert to Flutter compatible format"""
        data = super().to_representation(instance)
        return {
            'id': data['id'],
            'product_id': data['product_id'],
            'variant_id': data['variant_id'],
            'added_at': data['added_at']
        }

# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< WISHLIST SERIALIZER >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------

class WishlistSerializer(serializers.ModelSerializer):
    items = WishlistItemSerializer(many=True, read_only=True, source='wishlist_items')
    
    class Meta:
        model = Wishlist
        fields = ['id', 'user', 'items', 'total_items', 'created_at', 'updated_at']
        read_only_fields = ['total_items', 'created_at', 'updated_at']
