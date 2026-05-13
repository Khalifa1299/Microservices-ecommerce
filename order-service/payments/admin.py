# payments/admin.py
from django.contrib import admin
from .models import PaymentMethod, PaymentTransaction, Refund

@admin.register(PaymentMethod)
class PaymentMethodAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'cardholder_name', 'masked_card_number', 'card_type', 'expiry_date', 'is_default', 'created_at')
    list_filter = ('card_type', 'is_default', 'created_at')
    search_fields = ('user__email', 'user__username', 'cardholder_name', 'card_number')
    readonly_fields = ('masked_card_number', 'created_at', 'updated_at')
    fieldsets = (
        ('User Information', {
            'fields': ('user',)
        }),
        ('Card Details', {
            'fields': ('cardholder_name', 'card_number', 'masked_card_number', 'card_type', 'expiry_month', 'expiry_year')
        }),
        ('Settings', {
            'fields': ('is_default', 'billing_address_id', 'gateway_token')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    date_hierarchy = 'created_at'

class RefundInline(admin.TabularInline):
    model = Refund
    extra = 0
    fields = ('amount', 'reason', 'status', 'created_at')
    readonly_fields = ('created_at',)

@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'order', 'payment_method', 'amount', 'status', 'provider', 'transaction_id', 'created_at')
    list_filter = ('status', 'provider', 'created_at')
    search_fields = ('order__id', 'transaction_id', 'payment_method__cardholder_name')
    inlines = [RefundInline]
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at', 'updated_at')

@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ('transaction', 'amount', 'reason', 'status', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('transaction__order__id', 'reason')
    readonly_fields = ('created_at',)