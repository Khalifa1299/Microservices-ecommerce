# payments/views.py
from rest_framework import generics, status, viewsets
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.decorators import action
from rest_framework.views import APIView
from django.db import transaction as db_transaction
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import PaymentMethod, PaymentTransaction, Refund
from .serializers import (
    PaymentMethodSerializer,
    PaymentMethodCreateSerializer,
    PaymentMethodUpdateSerializer,
    PaymentTransactionSerializer,
    RefundSerializer
)
from .paymob import PaymobService
from orders.models import Order

class PaymentMethodViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing user payment methods.
    
    list: Get all payment methods for the authenticated user
    create: Add a new payment method
    retrieve: Get a specific payment method
    update/partial_update: Update payment method details
    destroy: Delete a payment method
    """
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        return PaymentMethod.objects.filter(user_id=self.request.user.id)
    
    def get_serializer_class(self):
        if self.action == 'create':
            return PaymentMethodCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return PaymentMethodUpdateSerializer
        return PaymentMethodSerializer
    
    def perform_create(self, serializer):
        """Create payment method for authenticated user"""
        serializer.save(user_id=self.request.user.id)
    
    def destroy(self, request, *args, **kwargs):
        """Delete payment method"""
        instance = self.get_object()
        
        # Get total count of user's payment methods
        total_methods = PaymentMethod.objects.filter(user_id=request.user.id).count()
        
        # Allow deletion if there are multiple methods
        # Or if it's the only one and not being used in pending orders
        if total_methods == 1:
            # Check if there are pending orders using this payment method
            # For now, we'll allow deletion of the last payment method
            pass
        
        # If deleting default and there are other methods, set another as default
        if instance.is_default and total_methods > 1:
            other_method = PaymentMethod.objects.filter(
                user_id=request.user.id
            ).exclude(id=instance.id).first()
            
            if other_method:
                other_method.is_default = True
                other_method.save()
        
        self.perform_destroy(instance)
        
        return Response({
            'success': True,
            'message': 'Payment method deleted successfully'
        }, status=status.HTTP_200_OK)
    
    
    @action(detail=True, methods=['post'])
    def set_default(self, request, pk=None):
        """Set a payment method as default"""
        payment_method = self.get_object()
        
        # Unset current default
        PaymentMethod.objects.filter(
            user_id=request.user.id,
            is_default=True
        ).update(is_default=False)
        
        # Set new default
        payment_method.is_default = True
        payment_method.save()
        
        serializer = self.get_serializer(payment_method)
        return Response(serializer.data)
    
    def list(self, request, *args, **kwargs):
        """List all payment methods with success wrapper"""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        return Response({
            'success': True,
            'data': serializer.data
        })
    
    def create(self, request, *args, **kwargs):
        """Create payment method with success wrapper"""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        
        # Return full details using the read serializer
        output_serializer = PaymentMethodSerializer(serializer.instance)
        
        return Response(
            output_serializer.data,
            status=status.HTTP_201_CREATED
        )
    
    def update(self, request, *args, **kwargs):
        """Update payment method with success wrapper"""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        
        # Return full details using the read serializer
        output_serializer = PaymentMethodSerializer(serializer.instance)
        
        return Response(output_serializer.data)

class PaymentTransactionCreateView(generics.CreateAPIView):
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        order_id = self.request.data.get('order')
        order = Order.objects.get(id=order_id, user_id=self.request.user.id, status='pending')
        with db_transaction.atomic():
            payment = serializer.save(order=order, amount=order.total_amount)
            if payment.status == 'completed':
                order.status = 'processing'
                order.save()

class PaymentTransactionDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = PaymentTransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return PaymentTransaction.objects.filter(order__user_id=self.request.user.id)

class RefundCreateView(generics.CreateAPIView):
    serializer_class = RefundSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        transaction_id = self.request.data.get('transaction')
        payment_transaction = PaymentTransaction.objects.get(id=transaction_id, order__user_id=self.request.user.id)
        with db_transaction.atomic():
            refund = serializer.save(
                transaction=payment_transaction,
                amount=min(payment_transaction.amount, self.request.data.get('amount', payment_transaction.amount))
            )
            if refund.status == 'processed':
                payment_transaction.status = 'refunded'
                payment_transaction.save()


# ─────────────────────────────────────────────────────────────────────────────
# Paymob
# ─────────────────────────────────────────────────────────────────────────────

class PaymobInitiateView(APIView):
    """
    POST /api/payments/paymob/initiate/
    Body: { "order_id": <int> }

    Runs the 3-step Paymob flow and returns the iframe URL + payment key.
    Also creates (or reuses) a pending PaymentTransaction record.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        order_id = request.data.get("order_id")
        if not order_id:
            return Response({"success": False, "message": "order_id is required"},
                            status=status.HTTP_400_BAD_REQUEST)

        order = Order.objects.filter(id=order_id, user_id=request.user.id).first()
        if not order:
            return Response({"success": False, "message": "Order not found"},
                            status=status.HTTP_404_NOT_FOUND)

        if order.status not in ("pending", "processing"):
            return Response({"success": False,
                             "message": "Order is not in a payable state"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            result = PaymobService.initiate(order, request.user.id)
        except Exception as e:
            return Response({"success": False, "message": str(e)},
                            status=status.HTTP_502_BAD_GATEWAY)

        # Upsert a PaymentTransaction so we can track it
        txn, _ = PaymentTransaction.objects.update_or_create(
            order=order,
            provider="paymob",
            defaults={
                "amount":          order.total_amount,
                "status":          "pending",
                "paymob_order_id": result["paymob_order_id"],
                "payment_key":     result["payment_key"],
            },
        )

        return Response({
            "success":         True,
            "payment_key":     result["payment_key"],
            "paymob_order_id": result["paymob_order_id"],
            "iframe_url":      result["iframe_url"],
            "transaction_id":  txn.id,
        }, status=status.HTTP_200_OK)


@method_decorator(csrf_exempt, name="dispatch")
class PaymobWebhookView(APIView):
    """
    POST /api/paymob/webhook/
    Paymob calls this after every transaction attempt.
    No auth required — we verify via HMAC instead.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        data = request.data
        cart = data.get("cart", data)  # Some versions of Paymob nest the payload under "cart"

        if not PaymobService.verify_hmac(data):
            return Response({"detail": "Invalid HMAC"}, status=status.HTTP_400_BAD_REQUEST)

        obj         = data.get("obj", data)
        success     = str(obj.get("success", "")).lower() == "true"
        pending     = str(obj.get("pending", "")).lower() == "true"
        paymob_txn_id  = str(obj.get("id", ""))
        paymob_order_id = str(obj.get("order", {}).get("id", "")) if isinstance(obj.get("order"), dict) else str(obj.get("order", ""))

        txn = PaymentTransaction.objects.filter(paymob_order_id=paymob_order_id).first()
        if not txn:
            return Response({"detail": "Transaction not found"}, status=status.HTTP_404_NOT_FOUND)

        with db_transaction.atomic():
            if success and not pending:
                txn.status         = "completed"
                txn.transaction_id = paymob_txn_id
                txn.order.status   = "processing"
                txn.order.save(update_fields=["status"])

            # TODO: clear cart via cart-service API (GET user_id from txn.order, call DELETE /api/cart/clear/)

            elif pending:
                txn.status = "pending"
            else:
                txn.status = "failed"
            txn.save(update_fields=["status", "transaction_id"])

        return Response({"detail": "ok"}, status=status.HTTP_200_OK)