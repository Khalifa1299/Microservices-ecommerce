# E-Commerce Microservices Platform

A production-grade Django microservices application for e-commerce, deployed on Kubernetes. Each service owns its domain, its database, and its API surface — they communicate over HTTP and Kafka.

---

## Architecture Overview

```
                          ┌─────────────────────────────────────┐
                          │         Nginx Ingress Controller     │
                          │         ecommerce.local (TLS)        │
                          └──────────────┬──────────────────────┘
                                         │  route by path
          ┌──────────┬───────────────────┼───────────┬──────────┐
          ▼          ▼                   ▼           ▼          ▼
   ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐
   │    Auth    │ │  Product   │ │   Order    │ │    Cart    │ │ Inventory  │
   │  :8001     │ │  :8002     │ │  :8003     │ │  :8004     │ │  :8005     │
   └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └────────────┘ └─────┬──────┘
         │              │              │                               │
         │         ┌────┴─────┐   ┌───┴────┐                    ┌────┴─────┐
         │         │  Kafka   │   │  Kafka │                    │  Kafka   │
         │         │ consumer │   │producer│                    │ consumer │
         │         └──────────┘   └───┬────┘                    └──────────┘
         │                            │
         │              ┌─────────────┘
         │              ▼
         │        ┌───────────┐
         │        │   Kafka   │  (KRaft, single broker)
         │        │  :9092    │
         │        └───────────┘
         │
         └────────────────────────────────────────────────────────────────┐
                                                                          │
   ┌──────────┐  ┌─────────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┴──┐
   │ auth-db  │  │ product-db  │  │ order-db │  │ cart-db  │  │inventory-db│
   │PostgreSQL│  │ PostgreSQL  │  │PostgreSQL│  │PostgreSQL│  │ PostgreSQL │
   └──────────┘  └─────────────┘  └──────────┘  └──────────┘  └────────────┘

   ┌────────────────────────────────────────────────────────────────────────┐
   │                         Redis (DB-partitioned)                         │
   │  DB0: auth Celery  │  DB1: product Celery  │  DB2: order Celery       │
   │  DB3: product cache│  DB4: auth cache      │  DB5: cart cache         │
   └────────────────────────────────────────────────────────────────────────┘

   ┌────────────────────────────────────────────────────────────────────────┐
   │                         Observability Stack                            │
   │  Prometheus → Grafana (dashboards)   OTel Collector → Grafana Tempo   │
   └────────────────────────────────────────────────────────────────────────┘
```

---

## Services

| Service | Port | Owns | Celery | Kafka |
|---|---|---|---|---|
| [auth-service](#auth-service) | 8001 | users, RBAC, JWT | ✓ (email tasks) | — |
| [product-service](#product-service) | 8002 | catalog, reviews, recommendations | ✓ (recommendation jobs) | consumer + producer |
| [order-service](#order-service) | 8003 | orders, payments, shipping | ✓ (payment tasks) | producer |
| [cart-service](#cart-service) | 8004 | cart, wishlist, coupons | — | — |
| [inventory-service](#inventory-service) | 8005 | stock, warehouses, analytics, POS | ✓ | consumer |

---

## Tech Stack

| Layer | Technology | Version |
|---|---|---|
| Framework | Django | 4.2.7 |
| API | Django REST Framework + SimpleJWT | 3.14 / 5.3 |
| App Server | Gunicorn | 21.2 |
| Database | PostgreSQL | 16 |
| Cache / Broker | Redis | 7 |
| Task Queue | Celery | 5.3.4 |
| Message Stream | Apache Kafka | 3.7.0 (KRaft) |
| Search | Algolia | 4.38.1 |
| Payments | Paymob (primary), Stripe | — |
| Tracing | OpenTelemetry SDK | 1.24.0 |
| Metrics | django-prometheus | 2.3.1 |
| ML | scikit-learn + numpy | 1.3 / 1.24 |
| Containers | Docker (multi-stage) | — |
| Orchestration | Kubernetes | 1.35 |
| Ingress | Nginx Ingress Controller | v1.14 |
| Trace backend | Grafana Tempo | 2.4.1 |
| Metrics backend | Prometheus + Grafana | — |

---

## Service Details

### Auth Service

**Port:** 8001 | **Namespace:** `ecommerce` | **DB:** `auth_db`

The only service that owns the `User` model. Issues and validates JWTs; all other services validate tokens locally using the shared `SECRET_KEY`.

**Django apps:** `users`

**Key models:**
- `User` — custom `AbstractUser`; email login, `account_status` (active / pending / banned), profile completion tracking
- `Role` / `AppPermission` — RBAC via many-to-many codename permissions
- `Address` — user addresses with validation score and default-address logic
- `DeviceSession` — per-device login tracking (device ID, platform, OS, IP, last seen)
- `TemporaryOTP` — time-limited OTP for email verification and password reset
- `UserActivity` — audit log (login, logout, password change, OTP, profile update, etc.)

**API endpoints:**

| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/token/` | Obtain JWT access + refresh tokens |
| POST | `/api/auth/token/refresh/` | Refresh access token |
| POST | `/api/auth/users/signup/` | Register new user |
| POST | `/api/auth/users/verify-otp/` | Verify email OTP |
| POST | `/api/auth/users/resend-otp/` | Resend OTP |
| POST | `/api/auth/users/login/` | Login |
| POST | `/api/auth/users/logout/` | Logout (blacklists refresh token) |
| GET/PUT | `/api/auth/users/profile/` | Current user profile |
| POST | `/api/auth/users/change-password/` | Change password |
| POST | `/api/auth/users/initiate-password-reset/` | Request password reset |
| POST | `/api/auth/users/reset-password/` | Complete password reset |
| GET/POST | `/api/auth/users/addresses/` | Address list / create |
| GET | `/api/auth/users/activities/` | User activity log |

---

### Product Service

**Port:** 8002 | **DB:** `product_db` | **Cache:** Redis DB 3 (TTL 5 min)

Owns the full product catalog, search, reviews, and ML-based recommendations.

**Django apps:** `products`, `reviews`, `recommendations`

**Key models:**
- `Category` — self-referential hierarchy (parent FK), slug, image, meta tags
- `Product` — name, description, `base_price`, `total_price` (computed with discounts), category, brand, tags (JSON), origin country
- `ProductVariant` — per-SKU stock, price override, `reserved_quantity`, `low_stock_threshold`, `reorder_point`
- `Discount` — percentage or fixed, product or variant scope, date-bounded, usage limits
- `ProductMerchandising` — search weight boost, popularity score, homepage feature flag
- `ProductAnalytics` — views, unique daily views, sales count, conversion rate
- `Review` — rating 1–5, title, comment; one per (product, user_id); approval workflow
- `UserProductInteraction` — interaction weights (view, add-to-cart, purchase, wishlist, search)
- `ProductSimilarity` — pre-computed similarity scores (category, tags, collaborative)
- `FrequentlyBoughtTogether` — association strength and confidence

**API endpoints:**

| Method | Path | Description |
|---|---|---|
| GET | `/api/products/categories/` | Category list |
| GET | `/api/products/products/` | Product list (filterable, searchable) |
| GET | `/api/products/products/<pk>/variants/` | Variants for a product |
| GET | `/api/products/products/<pk>/images/` | Images for a product |
| GET | `/api/products/search/` | Algolia unified search |
| GET | `/api/products/search/fallback/` | DB fallback search |
| GET/POST | `/api/products/discounts/` | Discount list / create |
| GET/POST | `/api/products/reviews/` | Review list / create |
| GET | `/api/products/products/<pk>/reviews/` | Reviews for a product |
| GET | `/api/recommendations/` | Personalized recommendations |

---

### Order Service

**Port:** 8003 | **DB:** `order_db`

Owns the full order lifecycle, multi-gateway payment processing, and multi-carrier shipping.

**Django apps:** `orders`, `payments`, `shipping`

**Key models:**
- `Order` — status (pending → processing → shipped → delivered → cancelled), payment method, subtotal, tax, shipping fee, coupon, address snapshots
- `OrderItem` — line item with variant ID, unit price, quantity
- `PaymentMethod` — tokenized card (stores last 4 digits only), gateway token, expiry, is_default
- `PaymentTransaction` — amount, status (pending / completed / failed / refunded), Paymob-specific fields
- `Refund` — linked to transaction, reason, status
- `Shipment` — carrier (Aramex / Bosta / MKH), tracking number, package dimensions/weight, label URL, estimated and actual delivery
- `ShippingRate` — cached rate quotes keyed by origin zip + destination zip + weight + dimensions
- `TrackingEvent` — carrier events timeline (location, event type, timestamp)

**API endpoints:**

| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/orders/orders/` | Order list / create |
| GET/PUT/DELETE | `/api/orders/orders/<pk>/` | Order detail |
| GET/POST | `/api/payments/payment-methods/` | Saved card list / add |
| POST | `/api/payments/transactions/` | Create payment transaction |
| POST | `/api/payments/refunds/` | Request refund |
| POST | `/api/payments/paymob/initiate/` | Initiate Paymob checkout |
| POST | `/api/payments/paymob/webhook/` | Paymob payment webhook |
| GET/POST | `/api/shipping/shipments/` | Shipment list / create |
| GET | `/api/shipping/shipments/<pk>/` | Shipment tracking |

---

### Cart Service

**Port:** 8004 | **DB:** `cart_db` | **Cache:** Redis DB 5 (TTL 30 min)

Lightweight service. No Celery, no Kafka — just cart state and coupon validation.

**Django app:** `cart`

**Key models:**
- `Cart` — per-user, holds coupon FK, computes `total_amount` on save
- `CartItem` — variant ID, quantity, unit price, subtotal; unique per (variant, cart)
- `Coupon` — code, percentage or fixed discount, date-bounded, `is_valid()` check
- `Wishlist` / `WishlistItem` — per-user wishlist; unique per (user, product)

**API endpoints:**

| Method | Path | Description |
|---|---|---|
| GET/POST | `/api/cart/carts/` | Cart list / create |
| GET/PUT/DELETE | `/api/cart/carts/<pk>/` | Cart detail |
| GET/POST | `/api/cart/cart-items/` | Cart item list / add |
| GET/PUT/DELETE | `/api/cart/cart-items/<pk>/` | Cart item detail |
| GET/POST | `/api/cart/wishlist/` | Wishlist list / create |
| GET/PUT/DELETE | `/api/cart/wishlist/<pk>/` | Wishlist detail |

---

### Inventory Service

**Port:** 8005 | **DB:** `inventory_db`

Multi-warehouse stock management with atomic reservations, movement audit trail, and daily sales analytics.

**Django apps:** `inventory`, `analytics`, `pos` (stub)

**Key models:**
- `Warehouse` — named location, `is_active`
- `StockLocation` — variant stock at a warehouse; `reserved_quantity`, `low_stock_threshold`, `reorder_point`; atomic `reserve_stock()` / `release_stock()` / `adjust_stock()` methods
- `StockMovement` — full audit trail; types: `stock_in`, `stock_out`, `reserve`, `release`, `adjustment`
- `DailySales` — aggregated: revenue, cost, orders, items sold, active orders, low-stock count; `profit` property
- `ProductDailyAnalytics` — per-product views, sales count, revenue; unique per (product, date)

**API endpoints:**

| Method | Path | Description |
|---|---|---|
| GET | `/api/inventory/warehouses/` | Warehouse list |
| GET | `/api/inventory/stock-locations/` | Stock by warehouse |
| GET | `/api/inventory/stock-movements/` | Movement audit log |
| POST | `/api/inventory/batch-update/` | Batch stock adjustment |
| GET | `/api/analytics/dashboard/` | Daily sales dashboard |

---

## Data Flow: Order Placement

```
Client → POST /api/orders/orders/
  └─ order-service creates Order (status: pending)
       └─ publishes Kafka event: order.created
            ├─ inventory-service consumes → reserves stock
            └─ product-service consumes → updates analytics
  └─ client calls POST /api/payments/paymob/initiate/
       └─ order-service calls Paymob API → returns payment key
  └─ Paymob calls POST /api/payments/paymob/webhook/
       └─ order-service updates Order status → processing
            └─ publishes Kafka event: payment.confirmed
```

---

## Running Locally (Docker Compose)

**Prerequisites:** Docker Desktop, `.env` file in repo root.

```env
# .env
DB_USER=your_db_user
DB_PASSWORD=your_db_password
SECRET_KEY=your-secret-key
```

```bash
docker compose up --build
```

Services start on ports 8001–8005. Each service runs migrations on startup via an entrypoint init step.

**Service URLs (local):**
- Auth: `http://localhost:8001`
- Product: `http://localhost:8002`
- Order: `http://localhost:8003`
- Cart: `http://localhost:8004`
- Inventory: `http://localhost:8005`

---

## Running on Kubernetes (Minikube)

### Prerequisites

```bash
minikube start
minikube addons enable ingress metrics-server
```

Add to `/etc/hosts` (or `C:\Windows\System32\drivers\etc\hosts`):
```
$(minikube ip)  ecommerce.local
```

### Deploy

```bash
# 1. Secrets
kubectl apply -f k8s/secrets/

# 2. Databases
kubectl apply -f k8s/databases/

# 3. Infrastructure (Redis, Kafka)
kubectl apply -f k8s/kafka/

# 4. Services
kubectl apply -f k8s/services/

# 5. Ingress
kubectl apply -f k8s/ingress/

# 6. Monitoring (Prometheus stack must be installed first)
kubectl apply -f k8s/monitoring/
```

### Check status

```bash
kubectl get pods -n ecommerce
kubectl get pods -n monitoring
```

### Access the API

```bash
# Get a JWT token
curl -k -X POST https://ecommerce.local/api/auth/token/ \
  -H "Content-Type: application/json" \
  -d '{"email": "user@example.com", "password": "password"}'
```

---

## Observability

### Prometheus Metrics

Each service exposes `/metrics` (via django-prometheus). ServiceMonitors scrape every 15 seconds.

Key metric families:
- `django_http_responses_total_by_status_view_method_total` — request rate, error rate
- `django_http_requests_latency_seconds_by_view_method_bucket` — P50 / P95 latency
- `django_db_execute_total` — database query rate (requires `django_prometheus.db.backends.postgresql` engine)

### Distributed Tracing (OpenTelemetry)

All services auto-instrument Django, PostgreSQL, Redis, HTTP requests, and Kafka. Spans are exported to the OTel Collector (`otel-collector.monitoring:4317`), which batches and forwards to Grafana Tempo.

To view traces: Grafana → Explore → Tempo data source.

```
Django service
  → OTel SDK (BatchSpanProcessor)
    → OTel Collector (OTLP gRPC :4317)
      → Grafana Tempo (:3200)
        → Grafana Explore
```

Environment variable to override the collector endpoint:
```bash
OTEL_EXPORTER_OTLP_ENDPOINT=otel-collector.monitoring:4317
```

---

## Security Model

- **Secret keys** — one `SECRET_KEY` per service, mounted from K8s Secrets; no defaults in code
- **JWT validation** — auth-service issues tokens; all other services validate locally using the shared secret (no round-trip to auth-service per request)
- **User model isolation** — only auth-service owns `User`; other services reference users by `user_id` (plain integer field)
- **Card data** — order-service stores only the last 4 digits; full card details go to the payment gateway only
- **Nginx headers** — `USE_X_FORWARDED_HOST` and `SECURE_PROXY_SSL_HEADER` configured on all services to trust Nginx Ingress headers

---

## Project Structure

```
microservices/
├── auth-service/
│   ├── auth_service/        # Django project (settings, urls, wsgi)
│   ├── users/               # Users app
│   ├── Dockerfile
│   └── requirements.txt
├── product-service/
│   ├── product_service/
│   ├── products/
│   ├── reviews/
│   ├── recommendations/
│   ├── Dockerfile
│   └── requirements.txt
├── order-service/
│   ├── order_service/
│   ├── orders/
│   ├── payments/
│   ├── shipping/
│   ├── Dockerfile
│   └── requirements.txt
├── cart-service/
│   ├── cart_service/
│   ├── cart/
│   ├── Dockerfile
│   └── requirements.txt
├── inventory-service/
│   ├── inventory_service/
│   ├── inventory/
│   ├── analytics/
│   ├── pos/
│   ├── Dockerfile
│   └── requirements.txt
├── k8s/
│   ├── databases/           # PostgreSQL StatefulSets + PVCs
│   ├── secrets/             # K8s Secret manifests (not committed)
│   ├── services/            # App Deployments + Services + Celery workers
│   ├── kafka/               # Kafka StatefulSet (KRaft mode)
│   ├── ingress/             # Nginx Ingress + cert-manager
│   └── monitoring/          # ServiceMonitors, OTel Collector, Grafana Tempo
├── docker-compose.yml
├── .gitignore
└── README.md
```

---

## Inter-Service Communication

Services call each other over HTTP using internal cluster DNS (K8s) or localhost ports (Docker Compose). Each service has environment variables for every other service URL:

```python
AUTH_SERVICE_URL    = http://auth-service:8001     # (set in other services)
PRODUCT_SERVICE_URL = http://product-service:8002
ORDER_SERVICE_URL   = http://order-service:8003
CART_SERVICE_URL    = http://cart-service:8004
INVENTORY_SERVICE_URL = http://inventory-service:8005
```

Event-driven communication uses Kafka topics for decoupled async flows (order placed → inventory reserve, payment confirmed → order status update, etc.).
