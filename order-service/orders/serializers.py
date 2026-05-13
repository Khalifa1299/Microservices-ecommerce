from rest_framework import serializers
from .models import Order, OrderItem, transaction

class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.SerializerMethodField()
    product_image = serializers.SerializerMethodField()

    class Meta:
        model = OrderItem
        fields = [
            'id', 'order', 'variant', 'quantity', 'unit_price',
            'created_at', 'product', 'product_name', 'product_image',
        ]
        depth = 0

    def get_product_name(self, obj):
        if obj.product:
            return obj.product.name
        if obj.variant and obj.variant.product:
            return obj.variant.product.name
        return None

    def get_product_image(self, obj):
        request = self.context.get('request')
        # Prefer variant image, fall back to product image
        img = None
        if obj.variant:
            img = obj.variant.images.first()
        if img is None and obj.product:
            img = obj.product.images.first()
        if img and img.image:
            return request.build_absolute_uri(img.image.url) if request else img.image.url
        return None

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = [
            'id', 'user', 'status', 'payment_method',
            'subtotal', 'discount_amount', 'coupon_code', 'tax_amount', 'shipping_fee', 'total_amount',
            'shipping_address', 'billing_address',
            'created_at', 'updated_at', 'items', 'tracking_number', 'carrier',
        ]
        read_only_fields = [
            'user', 'created_at', 'updated_at',
            'subtotal', 'discount_amount', 'coupon_code', 'tax_amount', 'total_amount', 'items',
        ]

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        with transaction.atomic():
            order = Order.objects.create(**validated_data)
            order_items = [OrderItem(order=order, **item_data) for item_data in items_data]
            OrderItem.objects.bulk_create(order_items)
            # Let signals handle total_amount update
        return order