# inventory/views.py
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.db import transaction
from django.http import Http404
from .models import Warehouse, StockLocation, StockMovement
from .serializers import (
    WarehouseSerializer, StockLocationSerializer, StockMovementSerializer,
    BatchStockUpdateSerializer
)

class WarehouseListView(generics.ListCreateAPIView):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ['name', 'location']
    ordering_fields = ['name', 'created_at']

class WarehouseDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [IsAuthenticated]

class StockLocationListView(generics.ListCreateAPIView):
    queryset = StockLocation.objects.all()
    serializer_class = StockLocationSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['variant', 'warehouse']
    search_fields = ['variant__sku']
    ordering_fields = ['stock', 'available_quantity']

class StockLocationDetailView(generics.RetrieveUpdateDestroyAPIView):
    serializer_class = StockLocationSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        # Override get_queryset to filter by variant_id instead of stock location id
        variant_id = self.kwargs['pk']
        return StockLocation.objects.filter(variant_id=variant_id)

    def get_object(self):
        queryset = self.get_queryset()
        obj = queryset.first()  # Get the first matching stock location
        if not obj:
            raise Http404(f"No StockLocation found for variant ID {self.kwargs['pk']}")
        return obj

class StockMovementListView(generics.ListAPIView):
    queryset = StockMovement.objects.all()
    serializer_class = StockMovementSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['stock_location', 'movement_type']
    ordering_fields = ['created_at']

class BatchStockUpdateView(generics.GenericAPIView):
    serializer_class = BatchStockUpdateSerializer
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updates = serializer.validated_data['updates']
        reason = serializer.validated_data['reason']

        with transaction.atomic():
            for update in updates:
                try:
                    location = StockLocation.objects.select_for_update().get(
                        variant_id=update['variant_id'],
                        warehouse_id=update['warehouse_id']
                    )
                    quantity = update['quantity']
                    location.adjust_stock(quantity, reason)
                except StockLocation.DoesNotExist:
                    return Response({'error': f"StockLocation not found for update: {update}"}, status=status.HTTP_400_BAD_REQUEST)
                except KeyError as e:
                    return Response({'error': f"Missing key in update: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({'success': 'Batch update complete'}, status=status.HTTP_200_OK)