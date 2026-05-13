# orders/views.py
from requests import request
from rest_framework import generics, status, viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db import transaction, IntegrityError
from django.db.models.signals import post_save
from django.shortcuts import get_object_or_404
from contextlib import contextmanager

from rest_framework import generics, permissions, status
from rest_framework.response import Response

from .models import Order, OrderItem
from .serializers import OrderSerializer, OrderItemSerializer
from .kafka_producer import publish_order_placed
from rest_framework.pagination import PageNumberPagination

import logging
logger = logging.getLogger(__name__)

# Custom pagination class
class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'pageSize'
    max_page_size = 100

# Context manager for temporarily disconnecting signals
@contextmanager
def temporarily_disconnect_signal(signal, receiver, sender):
    """
    Context manager to temporarily disconnect a signal and ensure it's reconnected.
    """
    signal.disconnect(receiver, sender=sender)
    try:
        yield
    finally:
        signal.connect(receiver, sender=sender)

# --------------------------------------------------------------------------------
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<< ORDER VIEWS >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# --------------------------------------------------------------------------------


class OrderViewSet(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    pagination_class = StandardResultsSetPagination

    def list(self, request):
        """List all orders for the authenticated user"""
        orders = Order.objects.filter(user_id=request.user.id).order_by('-created_at')
        paginator = self.pagination_class()
        page = paginator.paginate_queryset(orders, request)
        serializer = OrderSerializer(page, many=True, context={'request': request})
        return paginator.get_paginated_response({
            'success': True,
            'message': 'Orders retrieved successfully',
            'data': serializer.data
        })

    def create(self, request):
        """Create a new order from the user's cart"""
        if not request.user.is_authenticated:
            return Response({
                'success': False,
                'message': 'Authentication required to create an order.'
            }, status=status.HTTP_401_UNAUTHORIZED)

        from decimal import Decimal
        items_data = request.data.get('items', [])
        if not items_data:
            return Response({
                'success': False,
                'message': 'No items provided.'
            }, status=status.HTTP_400_BAD_REQUEST)

        serializer = OrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                'success': False,
                'message': 'Validation failed',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Capture price breakdown from cart BEFORE clearing it
        subtotal = sum(
        Decimal(str(item.get('unit_price', 0))) * item.get('quantity', 1)
        for item in items_data
                )
        shipping_fee = Decimal(str(request.data.get('shipping_fee', '0') or '0'))
        tax_amount = (subtotal * Decimal('0.14')).quantize(Decimal('0.01'))
        computed_total = subtotal + tax_amount + shipping_fee
        cart_coupon_code = request.data.get('coupon_code')
        cart_discount = Decimal(str(request.data.get('discount_amount', '0') or '0'))

        # Use a transaction to ensure atomicity and to avoid double-saving issues
        with transaction.atomic():
            # Use the context manager to temporarily disconnect the signal
            with temporarily_disconnect_signal(post_save, Order):
                try:
                    logger.debug(f"Creating order for user {request.user.id}")
                    order_data = serializer.validated_data.copy()
                    order_data['user_id'] = request.user.id
                    order_data['status'] = 'pending'
                    order = Order.objects.create(**order_data)
                    logger.debug(f"Order created with ID {order.id}")

                    # Create order items individually to ensure signals are triggered
                    for item in items_data:
                        if not item['variant_id'] or item['unit_price'] is None:
                            logger.error(f"Invalid variant or price for cart item {item.get('variant_id')}")
                            return Response({
                                'success': False,
                                'message': f'Invalid variant or price for cart item {item.get("variant_id")}.'
                            }, status=status.HTTP_400_BAD_REQUEST)

                        # Create each order item individually to trigger signals
                        order_item = OrderItem.objects.create(
                            order=order,
                            variant_id=item['variant_id'],
                            product_id=item['product_id'] if item['product_id'] else None,
                            quantity=item['quantity'],
                            unit_price=item['unit_price']
                        )
                        logger.debug(f"Created OrderItem {order_item.id} for order {order.id}")

                    # Persist full price breakdown
                    order.subtotal = subtotal
                    order.discount_amount = cart_discount
                    order.coupon_code = cart_coupon_code
                    order.tax_amount = tax_amount
                    order.shipping_fee = shipping_fee
                    order.total_amount = computed_total
                    order.save(update_fields=[
                        'subtotal', 'discount_amount', 'coupon_code',
                        'tax_amount', 'shipping_fee', 'total_amount'
                    ])
                    logger.debug(f"Order {order.id} total_amount updated to {order.total_amount}")

                    # Clear cart immediately only for cash/wallet payments.
                    # For card payments, cart is cleared by the Paymob webhook
                    # once payment is confirmed.
                    if order.payment_method in ('cash', 'wallet'):
                        # TODO: clear cart via cart-service API after order is created
                        pass

                except IntegrityError as db_e:
                    logger.error(f"Database integrity error during order creation: {str(db_e)}", exc_info=True)
                    return Response({
                        'success': False,
                        'message': f'Database error: {str(db_e)}'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
                except Exception as e:
                    logger.error(f"Unexpected error during order creation: {str(e)}", exc_info=True)
                    return Response({
                        'success': False,
                        'message': f'Unexpected error: {str(e)}'
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

            order.refresh_from_db()
            publish_order_placed(order)
            return Response({
                'success': True,
                'message': 'Order created successfully',
                'data': OrderSerializer(order).data
            }, status=status.HTTP_201_CREATED)
    
    def retrieve(self, request, pk=None):
        """Retrieve a specific order by ID"""
        try:
            order = get_object_or_404(Order, pk=pk, user_id=request.user.id)
            serializer = OrderSerializer(order, context={'request': request})
            return Response({
                'success': True,
                'message': 'Order retrieved successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({
                'success': False,
                'message': f'Error retrieving order: {str(e)}'
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def update(self, request, pk=None):
        """Update a specific order by ID"""
        order = get_object_or_404(Order, pk=pk, user_id=request.user.id)
        serializer = OrderSerializer(order, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'success': True,
                'message': 'Order updated successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
        return Response({
            'success': False,
            'message': 'Validation failed',
            'errors': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, pk=None):
        """Delete a specific order by ID"""
        order = get_object_or_404(Order, pk=pk, user_id=request.user.id)
        order.delete()
        return Response({
            'success': True,
            'message': 'Order deleted successfully'
        }, status=status.HTTP_204_NO_CONTENT)
        
        

class OrderCancelView(generics.GenericAPIView):
    """Cancel a specific order"""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user_id=self.request.user.id)

    def get_object(self):
        obj = super().get_object()
        if obj.user_id != self.request.user.id:
            raise PermissionDenied("You do not have permission to cancel this order")
        return obj

    def post(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status not in ('pending', 'processing'):
            return Response({
                'success': False,
                'message': 'Only pending or processing orders can be cancelled'
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # TODO: release reserved stock via inventory-service API
            instance.status = 'cancelled'
            instance.save()

        serializer = OrderSerializer(instance)
        return Response({
            'success': True,
            'message': 'Order cancelled successfully',
            'data': serializer.data
        }, status=status.HTTP_200_OK)

class OrderTrackingView(generics.RetrieveAPIView):
    """Get tracking information for a specific order"""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Order.objects.filter(user_id=self.request.user.id)

    def get_object(self):
        obj = super().get_object()
        if obj.user_id != self.request.user.id:
            raise PermissionDenied("You do not have permission to view this order's tracking")
        return obj

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Assuming tracking data is stored in Order model or a related model
        tracking_data = {
            'tracking_number': getattr(instance, 'tracking_number', 'N/A'),
            'carrier': getattr(instance, 'carrier', 'N/A'),
            'status': instance.status,
        }
        return Response({
            'success': True,
            'message': 'Tracking information retrieved',
            'data': tracking_data
        }, status=status.HTTP_200_OK)

class OrderItemsView(generics.ListAPIView):
    """List items for a specific order"""
    serializer_class = OrderItemSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        order_id = self.kwargs['order_id']
        return OrderItem.objects.filter(order_id=order_id)