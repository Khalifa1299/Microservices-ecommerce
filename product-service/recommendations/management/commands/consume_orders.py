import json
import logging
import time
from itertools import combinations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import F
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

from recommendations.models import FrequentlyBoughtTogether
from products.models import Product

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Consume orders.placed events and update FrequentlyBoughtTogether counts'

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
                    group_id='product-service-recommendations',
                    value_deserializer=lambda v: json.loads(v.decode('utf-8')),
                    auto_offset_reset='earliest',
                    enable_auto_commit=True,
                )
            except NoBrokersAvailable:
                logger.warning("Kafka not reachable yet, retrying in 5s...")
                time.sleep(5)

    def _process(self, payload):
        items = payload.get('items', [])
        product_ids = [item['product_id'] for item in items if item.get('product_id')]

        if len(product_ids) < 2:
            return

        # Verify products exist in this service's DB before writing pairs
        existing_ids = set(
            Product.objects.filter(id__in=product_ids).values_list('id', flat=True)
        )

        pairs = [
            (min(a, b), max(a, b))
            for a, b in combinations(existing_ids, 2)
        ]

        with transaction.atomic():
            for p1_id, p2_id in pairs:
                updated = FrequentlyBoughtTogether.objects.filter(
                    product1_id=p1_id, product2_id=p2_id
                ).update(frequency=F('frequency') + 1)

                if not updated:
                    FrequentlyBoughtTogether.objects.get_or_create(
                        product1_id=p1_id,
                        product2_id=p2_id,
                        defaults={'frequency': 1},
                    )

        logger.info(f"Processed order {payload.get('order_id')}: {len(pairs)} pairs updated")
