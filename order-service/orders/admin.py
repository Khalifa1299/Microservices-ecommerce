# orders/admin.py
from django.contrib import admin
from .models import Order, OrderItem
from payments.models import PaymentTransaction

class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 1
    fields = ('variant_id', 'quantity', 'unit_price', 'get_total_price')
    readonly_fields = ('get_total_price',)

    def get_total_price(self, obj):
        return obj.get_total_price()
    get_total_price.short_description = 'Total Price'

class PaymentInline(admin.TabularInline):
    model = PaymentTransaction
    extra = 0
    fields = ('amount', 'status', 'transaction_id', 'created_at')
    readonly_fields = ('created_at',)

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user_id', 'status', 'total_amount', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('user__username', 'id')
    inlines = [OrderItemInline, PaymentInline]
    date_hierarchy = 'created_at'

@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = ('order', 'variant_id', 'quantity', 'unit_price', 'get_total_price')
    list_filter = ('order__status',)
    search_fields = ('variant__sku', 'order__id')