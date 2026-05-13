# inventory/serializers.py
from rest_framework import serializers
from .models import Warehouse, StockLocation, StockMovement

class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = '__all__'

class StockLocationSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockLocation
        fields = [
            'id',
            'variant_id',  # Use _id suffix to get only the ID
            'warehouse_id',  # Use _id suffix to get only the ID
            'stock',
            'reserved_quantity',
            'low_stock_threshold',
            'reorder_point',
            'max_stock_level',
            'available_quantity'
        ]

class StockMovementSerializer(serializers.ModelSerializer):
    stock_location = StockLocationSerializer(read_only=True)

    class Meta:
        model = StockMovement
        fields = '__all__'

class BatchStockUpdateSerializer(serializers.Serializer):
    updates = serializers.ListField(
        child=serializers.DictField(
            child=serializers.IntegerField()  # e.g., {'variant_id': 1, 'warehouse_id': 1, 'quantity': 10}
        )
    )
    reason = serializers.CharField(max_length=100, default='batch_update')