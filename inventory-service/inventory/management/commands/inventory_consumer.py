import json
import logging
import time

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

from inventory.models import StockLocation, StockMovement

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Consume orders.placed events and decrement inventory stock'

    def handle(self, *args, **options):
        logger.info("Starting orders.placed consumer...")

        consumer = self._connect()
        logger.info("Connected to Kafka. Waiting for messages...")

        for message in consumer:
            try:
                self._process(message.value)
            except Exception as e:
                logger.error(f"Error processing message offset={message.offset}: {e}", exc_info=True)

    def _connect(self):
        """Retry until Kafka is reachable — broker may start after this pod."""
        while True:
            try:
                return KafkaConsumer(
                    'orders.placed',
                    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
                    group_id='inventory-service',
                    value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                    auto_offset_reset='earliest',
                    enable_auto_commit=True,
                )
            except NoBrokersAvailable:
                logger.warning("Kafka not reachable yet, retrying in 5s...")
                time.sleep(5)

    def _process(self, payload):
        order_id = payload.get('order_id')
        user_id = payload.get('user_id')
        items = payload.get('items', [])

        for item in items:
            variant_id = item.get('variant_id')
            quantity = item.get('quantity', 0)

            if not variant_id or quantity <= 0:
                logger.warning(f"Order {order_id}: skipping item with invalid variant_id={variant_id} quantity={quantity}")
                continue

            with transaction.atomic():
                # Lock the row so concurrent consumers don't double-decrement
                locations = StockLocation.objects.select_for_update().filter(variant_id=variant_id)

                remaining = quantity
                for location in locations:
                    if remaining <= 0:
                        break

                    deduct = min(remaining, location.stock)
                    if deduct <= 0:
                        continue

                    StockLocation.objects.filter(pk=location.pk).update(
                        stock=F('stock') - deduct
                    )
                    StockMovement.objects.create(
                        stock_location=location,
                        quantity=-deduct,
                        movement_type='out',
                        user_id=user_id,
                        notes=f"Order {order_id} fulfilled",
                    )
                    remaining -= deduct

                if remaining > 0:
                    logger.warning(
                        f"Order {order_id}: insufficient stock for variant {variant_id}. "
                        f"Requested {quantity}, shortfall {remaining}"
                    )

        logger.info(f"Processed order {order_id}: {len(items)} item(s) decremented from inventory")
