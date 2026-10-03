# Shop Commerce Platform & Synthetic Data Simulator

## Overview

This directory contains the backend for a small e-commerce platform: a
query-first Cassandra model, a day-level synthetic data simulator that feeds
it, a FastAPI layer for the domain, and a small read-only query UI for
exploring the data. There is no legacy system; the `payments` keyspace has been
retired in favour of `shop`.

The simulator is the main deliverable: the API and UI are reference surfaces,
while the day-to-day work is running the simulator to generate near real-world
data (with realistic quality issues) and its ground-truth manifest for the data
team.

---

## Quick start

Prerequisites: Docker, `uv` (or Python 3.11), and the project's `.venv`.

```bash
# 1. Start the local Cassandra node
cd backend_system
docker compose up -d

# 2. Install dependencies into the project venv (uv-managed, no pip)
uv sync

# 3. Generate 7 days of data (fresh keyspace)
uv run python simulate.py \
  --days 7 --start-date 2026-07-09 \
  --users-per-day 1500-2000 --conversion 1.7 \
  --seed 42 --reset

# 4. Explore the data in the browser
uv run uvicorn shop.api:app --host 0.0.0.0 --port 8100
# API docs:   http://localhost:8100/docs
# Data:       http://localhost:8100/ui
```

That produces ~12.6k sessions and ~218 orders (1.7% conversion) in
**under two minutes**. See [Performance](#performance) for why it is fast and
how to tune it.

---

## Repository layout

```
backend_system/
├── simulate.py                   # CLI entrypoint for the shop simulator
├── shop/                         # commerce platform package
│   ├── __init__.py
│   ├── config.py                 # sources, categories, discount + sim params
│   ├── ids.py                    # deterministic id generators
│   ├── id_factory.py             # runtime ids for API-created entities
│   ├── schema.py                 # shop keyspace DDL + INSERT statements
│   ├── catalog.py                # categories / products / variants
│   ├── people.py                 # users, PII, addresses
│   ├── traffic.py                # sessions, events, source attribution
│   ├── cart.py                   # carts, cart items, lucky check
│   ├── orders.py                 # orders, order items
│   ├── payments.py               # payment attempts, refunds
│   ├── dirty.py                  # data-quality issue injection + ledger
│   ├── writer.py                 # Cassandra writer (dry-run aware)
│   ├── repository.py             # read/update queries for the API
│   ├── service.py                # API business logic
│   ├── api_models.py             # Pydantic request/response schemas
│   ├── routes.py                 # FastAPI routes
│   ├── query.py                  # read-only CQL runner for the UI
│   ├── ui.py                     # interactive query UI (/ui)
│   ├── api.py                    # FastAPI app factory
│   └── simulator.py              # day-level orchestration
├── tests/                        # pytest suite
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

### Running your first simulation

Follow these steps in order. If you are brand new, do the dry run first - it
needs no database and proves your setup works.

**Step 0 - Prerequisites**

- Docker Desktop (for Cassandra), `uv`, and a terminal in `backend_system/`.
- Add `uv run` before `python` if you have not activated the project venv.

**Step 1 - Start Cassandra and wait for it to be ready**

```bash
cd backend_system
docker compose up -d
docker exec shop-cassandra nodetool status    # wait until the node shows "UN"
```

`UN` means "Up / Normal". The first start can take ~40 seconds. Do not run the
simulator before you see `UN`, or it will fail to connect.

**Step 2 - Create the schema and generate data**

```bash
uv run python simulate.py \
  --days 7 \
  --start-date 2026-07-09 \
  --users-per-day 1500-2000 \
  --conversion 1.7 \
  --reset
```

- `--reset` drops and recreates the `shop` keyspace, so every run starts clean.
- The command prints a JSON summary when it finishes.

**Step 3 - Read the summary**

At the end you will see something like:

```json
{
  "run_id": "run_20260709_7d_seed42",
  "sessions": 12598,
  "orders": 218,
  "converting_sessions": 218,
  "target_conversion_pct": 1.7,
  "actual_conversion_pct": 1.728,
  "injected_issues": 773,
  "row_counts": { "sessions": 12598, "orders": 218, "...": "..." }
}
```

`actual_conversion_pct` should be close to your `--conversion` target.

**Step 4 - Look at the data**

```bash
uv run uvicorn shop.api:app --host 0.0.0.0 --port 8100
```

Open <http://localhost:8100/ui>, click a preset (for example **Orders**), and
run it to see rows in a table.

**Step 5 - Re-run and vary it**

- Same `--seed` reproduces the exact same dataset.
- Change `--days`, `--users-per-day`, `--conversion` or `--seed` for a new one.

**Troubleshooting**

| Symptom | Cause / fix |
|---------|-------------|
| `NoHostAvailable` / connection refused | Cassandra not up yet - wait for `UN` in step 1 |
| `OperationTimedOut` on `DROP KEYSPACE` | Retry; a busy node can be slow to return. Add `--max-inflight 128` if it persists |
| Run seems slow | Lower `--days`, or raise `--max-inflight`. See [Performance](#performance) |
| Want to test without Cassandra | Add `--dry-run` to any command |

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
| `--max-inflight` | max concurrent in-flight writes (throughput vs memory) | `1024` |

### Usage

```bash
# from backend_system/ with the project's 3.11 venv

# 30 days, 500-2000 visitors/day, 3.5% conversion, reproducible
python simulate.py --days 30 --users-per-day 500-2000 --conversion 3.5 --seed 42

# fresh start (drops the shop keyspace) against local Cassandra
python simulate.py --days 90 --users-per-day 1000-5000 --conversion 4 --reset

# validate the generation logic without Cassandra
python simulate.py --days 7 --users-per-day 200-400 --conversion 5 --dry-run

# low-memory / gentle on a small node
python simulate.py --days 7 --users-per-day 1500-2000 --conversion 1.7 --max-inflight 128
```

### What it writes

A run populates the `shop` keyspace (see [Tables](#keyspace-and-tables)) and
records two provenance tables you can query afterwards:

- `simulation_runs` - the run parameters and actuals (sessions, orders,
  conversion). Query it to confirm what a dataset represents.
- `injected_issues` - the ground-truth ledger of every quality defect planted,
  with the affected table, column and value. Use it as a scoring key for
  cleaning jobs.

### Performance

The writer dispatches each insert with `execute_async` and keeps a bounded
window of in-flight writes (default `1024`), draining the oldest when the
window is full and flushing the rest on shutdown. This overlaps network
round-trips instead of paying one per row.

| Setting | Throughput | 7-day run |
|---------|-----------|-----------|
| synchronous (old) | ~5.6 sessions/sec | ~35 min |
| async, `--max-inflight 1024` (default) | ~69 sessions/sec | ~70 sec |

Tuning:

- **Faster:** raise `--max-inflight` (e.g. `2048`). Diminishing returns beyond
  what the node can absorb.
- **Gentler / lower memory:** lower it (e.g. `--max-inflight 128`) - useful on
  small nodes or when a `DROP KEYSPACE` timeout suggests the node is saturated.
- Writes are **not transactional**: a crash mid-run can leave partial data,
  which is fine for synthetic seeding. Re-run with `--reset` for a clean slate.

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

## Shop API

A FastAPI app over the `shop` keyspace for exercising the same domain rules
live. It is a reference/demo surface; the simulator remains the primary tool.

### Running

```bash
cd backend_system
uvicorn shop.api:app --host 0.0.0.0 --port 8100 --reload
```

Interactive docs at `http://localhost:8100/docs`. Env overrides:
`SHOP_CASSANDRA_HOST`, `SHOP_CASSANDRA_PORT`, `SHOP_KEYSPACE`.

### Endpoints (`/api/v1`)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/sessions` | start a session (guest or with `anonymous_id`) |
| GET | `/sessions/{id}` | fetch a session |
| POST | `/sessions/{id}/login` | log in/register, stitch `anonymous_id -> user_id` |
| GET | `/sessions/{id}/events` | session event stream |
| GET | `/categories` | list categories |
| GET | `/categories/{id}/products` | products in a category |
| GET | `/products/{id}/variants` | variants of a product |
| GET | `/variants/{id}` | variant by id |
| POST | `/carts` | create the session's active cart |
| GET | `/carts/{id}` | cart with items |
| POST | `/carts/{id}/items` | add a variant |
| DELETE | `/carts/{id}/items/{variant_id}` | remove a variant |
| POST | `/carts/{id}/lucky-check` | roll once/day; win = 20% off frozen to cart |
| POST | `/orders` | convert the cart (login required; 401 for guests) |
| GET | `/orders/{id}` | order with frozen item prices |
| GET | `/users/{id}/orders` | a user's orders |
| POST | `/payments` | create a payment attempt for an order |
| GET | `/payments/{id}` | payment by id |
| POST | `/payments/{id}/process\|complete\|fail\|refund` | payment lifecycle |

### Checkout flow

```
guest session -> cart -> add items -> [lucky-check]
  -> checkout -> login/register (stitch) -> POST /orders -> POST /payments
  -> process/complete -> order marked completed (or fail/refund)
```

Guests can browse and build carts but checkout returns **401** until they log
in; login adopts the session's cart. Order items snapshot the price paid, and
the cart's frozen Lucky Check discount carries into the order.

---

## Data explorer UI

A small read-only CQL console for understanding the shape of the data. Served
by the same FastAPI app.

```
http://localhost:8100/ui
```

- Query box with preset buttons (tables, categories, sessions, carts, orders,
  payments, lucky rolls, injected issues, simulation runs).
- **Read-only**: only single `SELECT` statements are accepted; anything
  containing `INSERT/UPDATE/DELETE/DROP/CREATE/...` is rejected.
- Results render as a table, capped at 200 rows, with a 10s query timeout.

> Cassandra uses CQL, not SQL - there are no joins or subqueries. This is a
> guided explorer, not a general database console.

---

## Technology stack

- **Python 3.11** (`uv` managed)
- **FastAPI + Uvicorn + Pydantic v2**
- **Cassandra 5.0** + `cassandra-driver`
- **Docker Compose** for local Cassandra (container `shop-cassandra`)
- **pytest / pytest-asyncio / httpx** for tests
- `structlog`, `prometheus-client`, `passlib`, `python-jose` available for
  later hardening

## Testing

```bash
pytest
```

`tests/test_simulator.py` runs without Cassandra (dry-run generator tests).
`tests/test_query.py` covers the read-only query guard. `tests/test_api.py` is
an integration suite that uses a dedicated `shop_test`
keyspace on `127.0.0.1:9042`; it is skipped automatically when Cassandra is
unreachable.

## License

Part of the Payments Orders System learning project.
