# Payments Orders System - Backend & Commerce Simulator

## Overview

This directory contains the backend for a small e-commerce platform and the
synthetic data simulator that feeds it.

There are two coexisting parts:

1. **Legacy payments system** (`orders_service/`, `payments_service/`,
   `main.py`) - the original FastAPI + Cassandra service. It stays in the
   `payments` keyspace and is left as-is.
2. **Commerce platform + simulator** (`shop/`, `simulate.py`) - the new,
   query-first Cassandra model for users, traffic, carts, orders, payments and
   a day-level synthetic data engine with realistic, intentionally dirty data.

The simulator is the main deliverable: APIs are a reference surface, but the
day-to-day work is running the simulator to generate near real-world data and
its ground-truth quality manifest for the data team.

---

## Repository layout

```
backend_system/
├── main.py                       # Legacy FastAPI app (payments keyspace)
├── cassandra_setup.py            # Legacy keyspace/table bootstrap
├── generate_data.py              # Legacy seed generator
├── simulate.py                   # NEW: CLI entrypoint for the shop simulator
├── shop/                         # NEW: commerce platform package
│   ├── __init__.py
│   ├── config.py                 # sources, categories, discount + sim params
│   ├── ids.py                    # deterministic id generators
│   ├── schema.py                 # shop keyspace DDL + INSERT statements
│   ├── catalog.py                # categories / products / variants
│   ├── people.py                 # users, PII, addresses
│   ├── traffic.py                # sessions, events, source attribution
│   ├── cart.py                   # carts, cart items, lucky check
│   ├── orders.py                 # orders, order items
│   ├── payments.py               # payment attempts, refunds
│   ├── dirty.py                  # data-quality issue injection + ledger
│   ├── writer.py                 # Cassandra writer (dry-run aware)
│   └── simulator.py              # day-level orchestration
├── orders_service/               # Legacy logical service module
├── payments_service/             # Legacy logical service module
├── docker-compose.yml            # Local Cassandra container
└── pyproject.toml                # uv project and dependencies
```

---

## Commerce Platform

### Entity model

```
Category ─< Product ─< Variant (SKU)
User ─< Session (source, anonymous_id) ─< Event
User / anonymous ─< Cart ─< CartItem ─> Variant
Session ── adopts ──> User          (identity stitch at login)
Cart ── converts ──> Order ─< OrderItem ─> Variant  (price SNAPSHOT)
Order ─< Payment                     (multiple attempts)
User / anonymous ─< LuckyRoll        (once per day)
```

Rules baked into the model:

- **Source is per session** (`utm_source`, `utm_medium`, `utm_campaign`,
  `referrer`, normalized `channel`).
- **No guest checkout** - anonymous visitors can browse and add to carts, but
  checkout requires login. Login is where `anonymous_id` is stitched to
  `user_id` via `identity_map`.
- **Money is `decimal` with an explicit `currency` column** everywhere.
- **Order items snapshot prices** at purchase time; orders never join to live
  catalog prices.
- **Payments allow multiple attempts** per order (attempt 1 fails, attempt 2
  succeeds, etc.).
- **No inventory logic.**
- **Lucky Check**: manual button on the cart, roll `1-1000`, win on
  `{7,8,9,10}` (0.4%), discount **20%** frozen onto the cart. Once per user per
  day, or per `anonymous_id` for guests. Roll value and discount are records,
  not inline `random()` calls.

### Keyspace and tables

Keyspace: `shop` (replication `SimpleStrategy`, `rf=1` for local).

**Identity & traffic**

| Table | Partition key | Clustering | Serves |
|-------|---------------|------------|--------|
| `users` | `user_id` | - | get user |
| `users_by_email` | `email` | - | login lookup |
| `user_addresses` | `user_id` | `address_id` | user's addresses (PII) |
| `sessions` | `session_id` | - | get session |
| `sessions_by_anonymous` | `anonymous_id` | `started_at`, `session_id` | a visitor's sessions |
| `sessions_by_user` | `user_id` | `started_at`, `session_id` | a user's sessions |
| `identity_map` | `anonymous_id` | - | anon -> user stitch |
| `identity_map_by_user` | `user_id` | `anonymous_id` | devices per user |
| `events` | `session_id` | `event_at`, `event_id` | raw funnel events |

**Catalog**

| Table | Partition key | Clustering | Serves |
|-------|---------------|------------|--------|
| `categories` | `category_id` | - | list categories |
| `products_by_category` | `category_id` | `product_id` | products in a category |
| `variants_by_product` | `product_id` | `variant_id` | variants of a product |
| `product_item_by_id` | `variant_id` | - | variant lookup |

**Cart**

| Table | Partition key | Clustering | Serves |
|-------|---------------|------------|--------|
| `carts` | `cart_id` | - | get cart |
| `cart_by_session` | `session_id` | - | active cart for a session |
| `cart_by_user` | `user_id` | `created_at`, `cart_id` | a user's carts |
| `cart_items` | `cart_id` | `variant_id` | items in a cart |

**Orders**

| Table | Partition key | Clustering | Serves |
|-------|---------------|------------|--------|
| `orders` | `order_id` | - | get order |
| `orders_by_user` | `user_id` | `created_at`, `order_id` | a user's orders |
| `order_items` | `order_id` | `variant_id` | items in an order (frozen prices) |

**Payments**

| Table | Partition key | Clustering | Serves |
|-------|---------------|------------|--------|
| `payments` | `payment_id` | - | get payment |
| `payments_by_order` | `order_id` | `attempt_no` | attempts for an order |

**Simulation metadata**

| Table | Partition key | Clustering | Serves |
|-------|---------------|------------|--------|
| `simulation_runs` | `run_id` | - | run params + actuals |
| `injected_issues` | `run_id` | `issue_id` | ground-truth quality ledger |

---

## Synthetic Data Simulator

Because nothing external calls the API, the simulator is run directly and
generates day-level data from a handful of inputs.

### Inputs (CLI flags)

| Flag | Meaning | Default |
|------|---------|---------|
| `--days` | number of days to simulate | `30` |
| `--users-per-day` | daily visitor range, `MIN-MAX` | `500-2000` |
| `--conversion` | target sessions -> orders percent | `3.5` |
| `--start-date` | first simulated day `YYYY-MM-DD` | today |
| `--seed` | RNG seed for reproducibility | `42` |
| `--host` / `--port` | Cassandra contact point | `127.0.0.1` / `9042` |
| `--keyspace` | target keyspace | `shop` |
| `--reset` | drop and recreate the keyspace first | off |
| `--dirty` | quality profile (`realistic` only for now) | `realistic` |
| `--dry-run` | generate in memory and print a summary, no DB writes | off |

### Usage

```bash
# from backend_system/ with the project's 3.11 venv

# 30 days, 500-2000 visitors/day, 3.5% conversion, reproducible
python simulate.py --days 30 --users-per-day 500-2000 --conversion 3.5 --seed 42

# fresh start (drops the shop keyspace) against local Cassandra
python simulate.py --days 90 --users-per-day 1000-5000 --conversion 4 --reset

# validate the generation logic without Cassandra
python simulate.py --days 7 --users-per-day 200-400 --conversion 5 --dry-run
```

### Day-level realism

- Volume inside `[MIN,MAX]` with a weekday/weekend curve, a mild growth trend
  and daily noise - not uniform.
- Intra-day distribution with business-hour peaks, a lunch dip and a
  late-night tail.
- New vs returning visitors: returning visitors reuse an `anonymous_id` across
  days (cookie), producing multi-day journeys.
- Source mix across organic / paid social / email / direct / referral /
  affiliate, with channel-dependent conversion and device-dependent behaviour.

### Funnel

```
visit -> session -> events (page/product views) -> add_to_cart -> cart
      -> [lucky check ~0.4% win] -> checkout -> login/register (stitch)
      -> order -> payment attempt(s) -> completed | failed | refunded
```

Sessions that do not convert become abandoned carts or pure browsing, which is
what the data team analyses. The target `conversion` is reconciled per day so
the aggregate sessions -> orders rate lands within a small tolerance of the
requested percentage (actuals are recorded in `simulation_runs`).

### Edge cases handled

Power users with many orders (Pareto), cart abandonment at every stage,
multiple carts/sessions per user, failed payments -> retries -> success or
abandonment, refunds and cancellations, anonymous carts never stitched, login
with no prior anonymous session, empty sessions, orphan carts, high-value
outlier orders, tiny orders, duplicate checkout clicks, and multi-currency.

### Intentional data-quality issues (`realistic`)

Injected at configurable rates and recorded in `injected_issues` so the ledger
doubles as a test oracle:

| Category | Examples |
|----------|----------|
| Nulls | missing email / phone / address |
| Format | mixed-case emails, trailing spaces, inconsistent country casing |
| Referential | order references a removed variant |
| Temporal | event after session end, duplicate timestamps |
| Financial | `discounted_price > price`, negative quantity, rounding drift |
| Duplication | duplicate payment attempt rows |
| Identity | one email mapped to two users |
| Enums | `Complete` vs `completed`, `usd` vs `USD` |
| Stale | sessions without `ended_at`, idle carts |

### Output

Cassandra only (keyspace `shop`), plus a printed run summary. The run manifest
is stored in `simulation_runs` and the injected-issue answer key in
`injected_issues`; no files are written by default.

---

## Legacy Payments System (unchanged)

The original FastAPI app and its services remain in the `payments` keyspace.
See the sections below.

### Running the legacy app

```bash
cd backend_system
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Endpoints: `POST /orders`, `GET /orders/{id}`, `PUT /orders/{id}/status`,
`POST /orders/{id}/cancel`, `POST /payments`, `GET /payments/{id}`,
`POST /payments/{id}/process|complete|fail|refund`, `GET /system/stats`.

### Legacy infrastructure

- **Cassandra 5.0** via `docker-compose.yml` (container
  `payments-orders-cassandra`).
- RabbitMQ / Redis / Prometheus + Grafana are planned but not wired into the
  runtime.

## Technology stack

- **Python 3.11** (`uv` managed)
- **FastAPI + Uvicorn + Pydantic v2**
- **Cassandra 5.0** + `cassandra-driver`
- **Docker Compose** for local Cassandra
- **pytest / pytest-asyncio / httpx** for tests
- `structlog`, `prometheus-client`, `passlib`, `python-jose` available for
  later hardening

## Testing

```bash
pytest
```

## License

Part of the Payments Orders System learning project.
