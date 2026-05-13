# Stock reservation on order add is handled via Kafka events (Phase 4).
# When order-service creates an OrderItem, it will publish a `order.item_added` event.
# inventory-service will consume that event and call StockLocation.reserve_stock().