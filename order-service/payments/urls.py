# payments/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PaymentMethodViewSet,
    PaymentTransactionCreateView,
    PaymentTransactionDetailView,
    RefundCreateView,
    PaymobInitiateView,
    PaymobWebhookView,
)

app_name = 'payments'

router = DefaultRouter()
router.register(r'payment-methods', PaymentMethodViewSet, basename='payment-method')

urlpatterns = [
    # Payment Methods (ViewSet routes)
    path('', include(router.urls)),
    
    # Transactions
    path('transactions/', PaymentTransactionCreateView.as_view(), name='transaction-create'),
    path('transactions/<int:pk>/', PaymentTransactionDetailView.as_view(), name='transaction-detail'),
    
    # Refunds
    path('refunds/', RefundCreateView.as_view(), name='refund-create'),

    # Paymob
    path('paymob/initiate/', PaymobInitiateView.as_view(), name='paymob-initiate'),
    path('paymob/webhook/', PaymobWebhookView.as_view(),  name='paymob-webhook'),
]