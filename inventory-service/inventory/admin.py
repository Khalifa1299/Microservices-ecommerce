# inventory/admin.py
from django.contrib import admin
from .models import Warehouse, StockLocation, StockMovement

# Inline for StockLocation under Warehouse
class StockLocationInline(admin.TabularInline):
    model = StockLocation
    extra = 1  # Number of empty forms to display
    fields = ('variant_id', 'stock', 'reserved_quantity', 'available_quantity', 'low_stock_threshold', 'reorder_point', 'max_stock_level')
    readonly_fields = ('available_quantity',)  

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('warehouse')

# Inline for StockMovement under StockLocation
class StockMovementInline(admin.TabularInline):
    model = StockMovement
    extra = 1
    fields = ('quantity', 'movement_type', 'notes', 'created_at')
    readonly_fields = ('created_at',)

@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ('name', 'location', 'is_active', 'created_at', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'location')
    inlines = [StockLocationInline]
    date_hierarchy = 'created_at'

@admin.register(StockLocation)
class StockLocationAdmin(admin.ModelAdmin):
    list_display = ('variant_id', 'warehouse', 'stock', 'reserved_quantity', 'available_quantity', 'needs_reorder')
    list_filter = ('warehouse__name', 'stock', 'reserved_quantity')  # Use actual fields
    search_fields = ('warehouse__name',)
    inlines = [StockMovementInline]
    readonly_fields = ('available_quantity', 'needs_reorder')  # Keep as readonly
    actions = ['reorder_stock']

    def reorder_stock(self, request, queryset):
        for location in queryset:
            if location.needs_reorder:
                location.adjust_stock(location.reorder_point - location.available_quantity, 'reorder_action')
        self.message_user(request, f"Reordered stock for {queryset.count()} locations.")

    reorder_stock.short_description = "Reorder stock for selected locations"

@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ('stock_location', 'quantity', 'movement_type', 'created_at', 'notes')
    list_filter = ('movement_type', 'created_at')
    search_fields = ('notes',)
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)