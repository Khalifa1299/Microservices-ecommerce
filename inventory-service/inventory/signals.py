# Stock reservation on cart add is handled via Kafka events (Phase 4).
# When cart-service creates a CartItem, it will publish a `cart.item_added` event.
# inventory-service will consume that event and call StockLocation.reserve_stock().