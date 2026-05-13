from django.db.models.signals import post_save
from django.dispatch import receiver
from django.db import transaction
from .models import ProductVariant
from inventory.models import StockLocation, Warehouse
import logging

logger = logging.getLogger(__name__)

@receiver(post_save, sender=ProductVariant)
def create_stock_location(sender, instance, created, **kwargs):
    """Create StockLocation for new ProductVariant"""
    try:
        if created and not hasattr(instance, 'stocklocation'):
            with transaction.atomic():
                # Get or create default warehouse
                warehouse = Warehouse.objects.filter(is_active=True).first()
                if warehouse is None:
                    warehouse = Warehouse.objects.create(
                        name="Orabi Store",
                        location="162 Rashid st next to Ahmed Orabi Metro Station",
                        is_active=True
                    )
                    logger.info(f"Created default warehouse: {warehouse.name}")
                
                # Create stock location
                stock_location = StockLocation.objects.create(
                    variant=instance,
                    warehouse=warehouse,
                    stock=getattr(instance, 'stock', 0),
                    reserved_quantity=getattr(instance, 'reserved_quantity', 0),
                    low_stock_threshold=getattr(instance, 'low_stock_threshold', 5),
                    reorder_point=getattr(instance, 'reorder_point', 10),
                    max_stock_level=getattr(instance, 'max_stock_level', 100),
                )
                logger.info(f"Created stock location for variant {instance.sku}: {stock_location.id}")
    except Exception as e:
        logger.error(f"Error creating stock location for variant {instance.sku}: {str(e)}")
        raise