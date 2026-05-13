# apps/shipping/views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend


from .models import Shipment
from .serializers import (
    ShipmentSerializer, 
    CreateShipmentSerializer, 
    RateRequestSerializer,
    ShippingRateSerializer
)
from .services import ShipmentService, RateService, TrackingService

import logging, traceback
logger = logging.getLogger(__name__)


class ShipmentViewSet(viewsets.ModelViewSet):
    queryset = Shipment.objects.all()
    serializer_class = ShipmentSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['status', 'carrier', 'order_id']
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shipment_service = ShipmentService()
        self.rate_service = RateService()
        self.tracking_service = TrackingService()
    
    def create(self, request, *args, **kwargs):
        """Create a new shipment"""
        serializer = CreateShipmentSerializer(data=request.data)

        if not serializer.is_valid():
            logger.error(
                f'Shipment serializer errors: {serializer.errors} | received: {request.data}'
            )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            shipment = self.shipment_service.create_shipment(serializer.validated_data)
            response_serializer = ShipmentSerializer(shipment)
            return Response(
                {'success': True, 'data': response_serializer.data},
                status=status.HTTP_201_CREATED
            )
        except Exception as e:
            
            logger.error(
                f'Shipment creation failed: {e}\n{traceback.format_exc()}'
            )
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    @action(detail=False, methods=['post'], url_path='get-rates')
    def get_rates(self, request):
        """Get shipping rates for a package"""
        serializer = RateRequestSerializer(data=request.data)
        
        if serializer.is_valid():
            try:
                rates = self.rate_service.get_shipping_rates(serializer.validated_data)
                response_serializer = ShippingRateSerializer(rates, many=True)
                logger.debug(f'Shipping rates calculated successfully: {response_serializer.data}')
                return Response(response_serializer.data)
            except Exception as e:
                return Response(
                    {'error': str(e)}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        else:
            logger.error('Shipping rate request validation failed: %s | Data: %s', serializer.errors, request.data)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'], url_path='track')
    def track(self, request, pk=None):
        """Get tracking information for a shipment"""
        try:
            tracking_data = self.tracking_service.track_shipment(pk)
            return Response(tracking_data)
        except ValueError as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='validate-address')
    def validate_address(self, request):
        """Validate an address"""
        try:
            result = self.address_service.validate_address(request.data)
            return Response(result)
        except Exception as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_400_BAD_REQUEST
            )
    
    @action(detail=False, methods=['get'], url_path='by-order/(?P<order_id>[^/.]+)')
    def by_order(self, request, order_id=None):
        """Get shipments by order ID"""
        if not order_id:
            return Response(
                {'error': 'order_id parameter is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        shipments = Shipment.objects.filter(order_id=order_id)
        serializer = ShipmentSerializer(shipments, many=True)
        return Response(serializer.data)
