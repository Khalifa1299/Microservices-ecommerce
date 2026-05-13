import json
import logging
from kafka import KafkaProducer
from django.conf import settings

logger = logging.getLogger(__name__)

_producer = None


def get_producer():
    """Return a module-level singleton KafkaProducer, creating it on first call."""
    global _producer
    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: str(k).encode('utf-8'),
            # Wait for the leader to acknowledge the write.
            # acks=1 balances durability and speed for dev.
            acks=1,
            retries=3,
        )
    return _producer


def publish_order_placed(order):
    """
    Publish an orders.placed event after an order is successfully created.
    Wrapped in try/except — Kafka unavailability must never break order creation.
    """
    try:
        payload = {
            'order_id': order.id,
            'user_id': order.user_id,
            'items': [
                {
                    'product_id': item.product_id,
                    'variant_id': item.variant_id,
                    'quantity': item.quantity,
                }
                for item in order.items.all()
            ],
        }

        get_producer().send(
            topic='orders.placed',
            key=order.id,       # route by order_id → consistent partition
            value=payload,
        )
        logger.info(f"Published orders.placed event for order {order.id}")

    except Exception as e:
        # Log but do not re-raise — order creation must succeed regardless
        logger.error(f"Failed to publish orders.placed for order {order.id}: {e}")
