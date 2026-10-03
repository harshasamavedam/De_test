"""Day-level synthetic data simulator for the shop domain.

Given a small set of inputs (days, daily visitor range, target conversion, a
seed), the simulator generates realistic, intentionally dirty data across the
whole funnel: traffic -> sessions/events -> carts -> orders -> payments.

Conversion is reconciled per day so the aggregate sessions -> orders rate lands
close to the requested percentage.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from . import config, ids
from .cart import CartFactory, CART_STATUS_ABANDONED, CART_STATUS_CONVERTED, compute_cart_totals
from .catalog import Catalog
from .dirty import IssueLedger
from .orders import (
    build_order_items,
    compute_order_totals,
    shipping_address_snapshot,
)
from .payments import PaymentFactory
from .people import PeopleFactory
from .traffic import TrafficFactory
from .writer import Writer

# Funnel tuning
RETURNING_VISITOR_RATE = 0.35
NEW_USER_AT_CHECKOUT_RATE = 0.60
LUCKY_ATTEMPT_RATE = 0.50
BROWSING_SESSION_RATE = 0.55
EXTRA_ABANDONED_CART_RATE = 0.06
HIGH_VALUE_ORDER_RATE = 0.03

# Order outcome mix
ORDER_OUTCOMES = (
    ("completed", 88),
    ("refunded", 5),
    ("processing", 4),
    ("cancelled", 3),
)


@dataclass
class SimParams:
    days: int = config.DEFAULT_DAYS
    users_per_day: tuple[int, int] = config.DEFAULT_USERS_PER_DAY
    conversion: Decimal = config.DEFAULT_CONVERSION
    start_date: date = field(default_factory=date.today)
    seed: int = config.DEFAULT_SEED
    keyspace: str = config.DEFAULT_KEYSPACE
    dirty: str = config.DEFAULT_DIRTY_PROFILE


class Simulator:
    def __init__(self, params: SimParams, writer: Writer):
        self.params = params
        self.writer = writer
        self.run_id = ids.run_id(params.seed, params.start_date, params.days)
        self.ledger = IssueLedger(self.run_id, params.seed, params.dirty)
        self.rng = random.Random(params.seed)
        self.catalog = Catalog(params.seed)
        self.people = PeopleFactory(params.seed, self.ledger, self.catalog)
        self.traffic = TrafficFactory(params.seed, self.ledger)
        self.carts = CartFactory(params.seed, self.ledger, self.catalog)
        self.payments = PaymentFactory(params.seed, self.ledger)

        self.anon_pool: list[str] = []
        self.anon_to_user: dict[str, str] = {}
        self.users_by_id: dict[str, dict] = {}
        self.user_counter = 0
        self.order_counter = 0
        self.customer_counter = 0
        self._seen_stitch: set[str] = set()

        self.actuals = {
            "sessions": 0,
            "orders": 0,
            "converting_sessions": 0,
        }

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------
    def run(self, reset: bool = False) -> dict:
        self.writer.connect(reset=reset)
        self._write_catalog()
        for offset in range(self.params.days):
            day = self.params.start_date + timedelta(days=offset)
            self._simulate_day(day, offset)
        self._write_run_metadata()
        self.writer.close()
        return self._summary()

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------
    def _write_catalog(self) -> None:
        for category in self.catalog.categories:
            self.writer.write("categories", category)
        variant_counts = self.catalog.variant_count_by_product()
        for product in self.catalog.products:
            self.writer.write(
                "products_by_category",
                {
                    "category_id": product["category_id"],
                    "product_id": product["product_id"],
                    "product_name": product["product_name"],
                    "brand": product["brand"],
                    "variant_count": variant_counts.get(product["product_id"], 0),
                    "created_at": datetime.utcnow(),
                },
            )
        for v in self.catalog.variants:
            self.writer.write(
                "variants_by_product",
                {
                    "product_id": v["product_id"],
                    "variant_id": v["variant_id"],
                    "category_id": v["category_id"],
                    "product_name": v["product_name"],
                    "variant_name": v["variant_name"],
                    "sku": v["sku"],
                    "attributes": v["attributes"],
                    "price": v["price_usd"],
                    "discounted_price": v["discounted_price_usd"],
                    "currency": "USD",
                    "is_active": v["is_active"],
                    "created_at": datetime.utcnow(),
                },
            )
            self.writer.write(
                "product_item_by_id",
                {
                    "variant_id": v["variant_id"],
                    "product_id": v["product_id"],
                    "category_id": v["category_id"],
                    "product_name": v["product_name"],
                    "variant_name": v["variant_name"],
                    "sku": v["sku"],
                    "attributes": v["attributes"],
                    "price": v["price_usd"],
                    "discounted_price": v["discounted_price_usd"],
                    "currency": "USD",
                    "is_active": v["is_active"],
                },
            )

    # ------------------------------------------------------------------
    # Day simulation
    # ------------------------------------------------------------------
    def _simulate_day(self, day: date, offset: int) -> None:
        session_count = self._daily_volume(offset)
        specs = []
        for seq in range(1, session_count + 1):
            returning, anon, user_id = self._pick_visitor()
            started_at = self._start_time(day)
            session = self.traffic.make_session(day, seq, anon, user_id, started_at)
            specs.append(session)
            self.actuals["sessions"] += 1

        target_orders = round(session_count * float(self.params.conversion) / 100)
        if self.params.conversion > 0:
            target_orders = max(1, target_orders)
        target_orders = min(target_orders, session_count)
        weights = [
            config.CHANNELS[s["channel"]]["conversion_multiplier"] for s in specs
        ]
        converting = self._weighted_sample_without_replacement(weights, target_orders)

        for index, session in enumerate(specs):
            self._simulate_session(session, index in converting, day)

    def _daily_volume(self, offset: int) -> int:
        low, high = self.params.users_per_day
        base = self.rng.randint(low, high)
        weekday_weight = config.WEEKDAY_VOLUME_WEIGHTS[(self.params.start_date.weekday() + offset) % 7]
        growth = (1 + config.DAILY_GROWTH_RATE) ** offset
        noise = self.rng.uniform(0.92, 1.08)
        return max(1, int(base * weekday_weight * growth * noise))

    def _start_time(self, day: date) -> datetime:
        hour = self.rng.choices(range(24), weights=config.HOUR_WEIGHTS, k=1)[0]
        return datetime.combine(
            day,
            time(hour, self.rng.randint(0, 59), self.rng.randint(0, 59)),
        )

    def _pick_visitor(self):
        if self.anon_pool and self.rng.random() < RETURNING_VISITOR_RATE:
            anon = self.rng.choice(self.anon_pool)
            return True, anon, self.anon_to_user.get(anon)
        anon = self.traffic.new_anonymous()
        self.anon_pool.append(anon)
        return False, anon, None

    # ------------------------------------------------------------------
    # Session simulation
    # ------------------------------------------------------------------
    def _simulate_session(self, session: dict, converting: bool, day: date) -> None:
        rng = self.rng
        outcome: dict = {"logged_in": session["user_id"] is not None}
        product_views: list[dict] = []

        if converting:
            self._simulate_converting(session, day, outcome, product_views)
        else:
            self._simulate_non_converting(session, day, outcome, product_views)

        outcome["product_views"] = product_views
        events = self.traffic.events_for(session, outcome)
        self._write_session(session)
        self.writer.write_many("events", events)

    def _simulate_converting(self, session, day, outcome, product_views):
        rng = self.rng
        user = self._ensure_user(session, day)
        session["user_id"] = user["user_id"]
        outcome["logged_in"] = True

        currency = config.CURRENCY_BY_COUNTRY.get(user.get("country") or "US", "USD")
        if currency not in config.CURRENCY_RATES_FROM_USD:
            currency = "USD"
        rate = config.CURRENCY_RATES_FROM_USD[currency]

        # product discovery before cart
        variants = self.rng.sample(
            self.catalog.active_variants(),
            min(self.rng.randint(1, 3), len(self.catalog.variants)),
        )
        for v in variants:
            product_views.append({"product_id": v["product_id"], "variant_id": v["variant_id"]})

        cart_id = self.carts.next_cart_id(day)
        items = self.carts.build_items(rate, currency)

        # high-value outlier
        if self.rng.random() < HIGH_VALUE_ORDER_RATE and items:
            item = self.rng.choice(items)
            item["quantity"] *= self.rng.randint(3, 8)
            item["line_total"] = (item["unit_discounted_price"] * item["quantity"]).quantize(Decimal("0.01"))
            self.rng.shuffle(items)

        # lucky check (optional click)
        roll = None
        discount_pct = Decimal("0")
        if self.rng.random() < LUCKY_ATTEMPT_RATE:
            roll = self.carts.lucky_check(
                config.LUCKY_SCOPE_USER, user["user_id"], cart_id, day,
                session["started_at"] + timedelta(minutes=5),
            )
            if roll and roll["won"]:
                discount_pct = roll["discount_pct"]

        totals = compute_cart_totals(items, discount_pct)
        order_created = session["started_at"] + timedelta(minutes=self.rng.randint(6, 40))

        order_id = self._next_order_id(day)

        # write the cart once, already pointing at the order it converted into
        self._write_cart(
            cart_id, session, user["user_id"], items, totals, CART_STATUS_CONVERTED,
            roll, order_id=order_id, currency=currency,
            created_at=session["started_at"],
        )

        order_items = build_order_items(items, currency, order_id)
        order_totals = compute_order_totals(
            order_items, discount_pct, ledger=self.ledger, order_id=order_id
        )
        order_status = self._weighted(rng, ORDER_OUTCOMES)
        session_source = session["source"]

        # every converted order snapshots a shipping address (PII)
        address = self._address_for(user)

        order = {
            "order_id": order_id,
            "user_id": user["user_id"],
            "cart_id": cart_id,
            "session_id": session["session_id"],
            "anonymous_id": session["anonymous_id"],
            "source": session_source,
            "channel": session["channel"],
            "status": self.ledger.status_casing("orders", order_id, order_status),
            "currency": self.ledger.currency_casing("orders", order_id, currency),
            "item_count": order_totals["item_count"],
            "subtotal": order_totals["subtotal"],
            "discount_pct": order_totals["discount_pct"],
            "discount_amount": order_totals["discount_amount"],
            "discount_reason": "lucky_check" if discount_pct > 0 else "",
            "tax_amount": order_totals["tax_amount"],
            "shipping_amount": order_totals["shipping_amount"],
            "total_amount": order_totals["total_amount"],
            "shipping_address": shipping_address_snapshot(user, address),
            "created_at": order_created,
            "updated_at": order_created + timedelta(minutes=self.rng.randint(1, 120)),
        }
        self.writer.write("orders", order)
        self.writer.write("orders_by_user", {
            "user_id": user["user_id"],
            "created_at": order_created,
            "order_id": order_id,
            "status": order_status,
            "total_amount": order_totals["total_amount"],
            "currency": currency,
            "item_count": order_totals["item_count"],
        })
        self.writer.write_many("order_items", order_items)
        self.actuals["orders"] += 1

        # payments
        attempts = self.payments.simulate_attempts(
            order_id, user["user_id"], order_totals["total_amount"], currency,
            order_status, order_created, day,
        )
        for attempt in attempts:
            attempt["currency"] = self.ledger.currency_casing("payments", attempt["payment_id"], attempt["currency"])
            attempt["metadata"] = {"source": config.SYNTHETIC_MARKER}
            self.writer.write("payments", attempt)
            self.writer.write("payments_by_order", {
                "order_id": order_id,
                "attempt_no": attempt["attempt_no"],
                "payment_id": attempt["payment_id"],
                "status": attempt["status"],
                "amount": attempt["amount"],
                "currency": attempt["currency"],
                "method": attempt["method"],
                "gateway": attempt["gateway"],
                "created_at": attempt["created_at"],
                "completed_at": attempt["completed_at"],
                "failed_at": attempt["failed_at"],
            })

        # optional second order same day (power user)
        if self.rng.random() < config.RETURN_ORDER_RATE:
            self._place_extra_order(session, user, day, currency, rate)

        outcome["cart_id"] = cart_id
        outcome["cart_items"] = items
        outcome["lucky_check"] = roll
        outcome["checkout"] = True
        outcome["order_id"] = order_id
        self.actuals["converting_sessions"] += 1

    def _simulate_non_converting(self, session, day, outcome, product_views):
        rng = self.rng
        # browsing-only session
        if rng.random() < 1 - config.CART_RATE:
            views = rng.sample(
                self.catalog.active_variants(),
                min(rng.randint(1, 4), len(self.catalog.variants)),
            )
            for v in views:
                product_views.append({"product_id": v["product_id"], "variant_id": v["variant_id"]})
            return

        user_id = session["user_id"]
        currency = "USD"
        if user_id and user_id in self.users_by_id:
            currency = config.CURRENCY_BY_COUNTRY.get(
                self.users_by_id[user_id].get("country") or "US", "USD"
            )
        rate = config.CURRENCY_RATES_FROM_USD.get(currency, Decimal("1.00"))

        cart_id = self.carts.next_cart_id(day)
        items = self.carts.build_items(rate, currency)
        roll = None
        discount_pct = Decimal("0")
        scope_type = config.LUCKY_SCOPE_USER if user_id else config.LUCKY_SCOPE_ANON
        scope_id = user_id or session["anonymous_id"]
        if rng.random() < LUCKY_ATTEMPT_RATE:
            roll = self.carts.lucky_check(
                scope_type, scope_id, cart_id, day, session["started_at"] + timedelta(minutes=4)
            )
            if roll and roll["won"]:
                discount_pct = roll["discount_pct"]

        totals = compute_cart_totals(items, discount_pct)
        self._write_cart(
            cart_id, session, user_id, items, totals, CART_STATUS_ABANDONED,
            roll, order_id=None, currency=currency, created_at=session["started_at"],
        )

        # rare second abandoned cart in the same session
        if rng.random() < EXTRA_ABANDONED_CART_RATE:
            cart2 = self.carts.next_cart_id(day)
            items2 = self.carts.build_items(rate, currency)
            totals2 = compute_cart_totals(items2, Decimal("0"))
            self._write_cart(
                cart2, session, user_id, items2, totals2, CART_STATUS_ABANDONED,
                roll=None, order_id=None, currency=currency,
                created_at=session["started_at"] + timedelta(minutes=3),
            )
            # stale cart quality issue
            if self.ledger.chance("stale_cart_idle"):
                self.ledger.record(
                    "carts", cart2, "updated_at", "stale_cart_idle", None,
                    "stuck_active",
                )

        outcome["cart_id"] = cart_id
        outcome["cart_items"] = items
        outcome["lucky_check"] = roll
        outcome["checkout"] = False

    def _place_extra_order(self, session, user, day, currency, rate):
        cart_id = self.carts.next_cart_id(day)
        items = self.carts.build_items(rate, currency)
        totals = compute_cart_totals(items, Decimal("0"))
        created = session["started_at"] + timedelta(minutes=self.rng.randint(45, 180))
        order_id = self._next_order_id(day)
        order_items = build_order_items(items, currency, order_id)
        order_totals = compute_order_totals(order_items, Decimal("0"), order_id=order_id)
        address = self._address_for(user)
        self.writer.write("carts", self._cart_row(
            cart_id, session, user["user_id"], items, totals, CART_STATUS_CONVERTED,
            None, order_id, currency,
        ))
        self.writer.write_many("cart_items", [
            self._cart_item_row(cart_id, i, currency, created) for i in items
        ])
        self.writer.write("cart_by_session", {
            "session_id": session["session_id"],
            "cart_id": cart_id,
            "user_id": user["user_id"],
            "status": CART_STATUS_CONVERTED,
            "updated_at": created,
        })
        self.writer.write("cart_by_user", {
            "user_id": user["user_id"],
            "created_at": created,
            "cart_id": cart_id,
            "status": CART_STATUS_CONVERTED,
            "total": totals["total"],
            "currency": currency,
        })
        self.writer.write("orders", {
            "order_id": order_id,
            "user_id": user["user_id"],
            "cart_id": cart_id,
            "session_id": session["session_id"],
            "anonymous_id": session["anonymous_id"],
            "source": session["source"],
            "channel": session["channel"],
            "status": "processing",
            "currency": currency,
            "item_count": order_totals["item_count"],
            "subtotal": order_totals["subtotal"],
            "discount_pct": Decimal("0"),
            "discount_amount": Decimal("0"),
            "discount_reason": "",
            "tax_amount": order_totals["tax_amount"],
            "shipping_amount": order_totals["shipping_amount"],
            "total_amount": order_totals["total_amount"],
            "shipping_address": shipping_address_snapshot(user, address),
            "created_at": created,
            "updated_at": created,
        })
        self.writer.write("orders_by_user", {
            "user_id": user["user_id"],
            "created_at": created,
            "order_id": order_id,
            "status": "processing",
            "total_amount": order_totals["total_amount"],
            "currency": currency,
            "item_count": order_totals["item_count"],
        })
        self.writer.write_many("order_items", order_items)
        self.actuals["orders"] += 1

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    def _ensure_user(self, session, day) -> dict:
        existing_id = session["user_id"]
        if existing_id and existing_id in self.users_by_id:
            self._stitch(session["anonymous_id"], existing_id, session["started_at"])
            return self.users_by_id[existing_id]

        if self.users_by_id and self.rng.random() > NEW_USER_AT_CHECKOUT_RATE:
            # log in to an existing account on a new device
            user = self.rng.choice(list(self.users_by_id.values()))
            self._stitch(session["anonymous_id"], user["user_id"], session["started_at"])
            return user

        # register a brand-new user at checkout
        self.user_counter += 1
        user = self.people.create_user(self.user_counter, session["started_at"])
        self.users_by_id[user["user_id"]] = user
        self.writer.write("users", user)
        if user["email"]:
            self.writer.write("users_by_email", {
                "email": user["email"],
                "user_id": user["user_id"],
                "created_at": user["created_at"],
            })
        if self.rng.random() < 0.7:
            address = self.people.address_for(self.customer_counter + 1, user)
            self.customer_counter += 1
            self.writer.write("user_addresses", {
                "user_id": address[0], "address_id": address[1], "label": address[2],
                "full_name": address[3], "line1": address[4], "line2": address[5],
                "city": address[6], "region": address[7], "postal_code": address[8],
                "country": address[9], "phone": address[10], "is_default": address[11],
                "created_at": address[12],
            })
        self._stitch(session["anonymous_id"], user["user_id"], session["started_at"])
        return user

    def _stitch(self, anonymous_id: str, user_id: str, when: datetime) -> None:
        self.anon_to_user[anonymous_id] = user_id
        if anonymous_id in self._seen_stitch:
            return
        self._seen_stitch.add(anonymous_id)
        self.writer.write("identity_map", {
            "anonymous_id": anonymous_id,
            "user_id": user_id,
            "first_seen": when,
            "linked_at": when,
            "link_source": "checkout_login",
        })
        self.writer.write("identity_map_by_user", {
            "user_id": user_id,
            "anonymous_id": anonymous_id,
            "first_seen": when,
            "linked_at": when,
        })

    def _address_for(self, user):
        address = self.people.address_for(self.customer_counter + 1, user)
        self.customer_counter += 1
        self.writer.write("user_addresses", {
            "user_id": address[0], "address_id": address[1], "label": address[2],
            "full_name": address[3], "line1": address[4], "line2": address[5],
            "city": address[6], "region": address[7], "postal_code": address[8],
            "country": address[9], "phone": address[10], "is_default": address[11],
            "created_at": address[12],
        })
        return address

    # ------------------------------------------------------------------
    # Row builders / writers
    # ------------------------------------------------------------------
    def _next_order_id(self, day):
        self.order_counter += 1
        return f"ord_{day:%Y%m%d}_{self.order_counter:07d}"

    def _write_session(self, session: dict) -> None:
        self.writer.write("sessions", {
            "session_id": session["session_id"],
            "anonymous_id": session["anonymous_id"],
            "user_id": session["user_id"],
            "source": session["source"],
            "utm_source": session["utm_source"],
            "utm_medium": session["utm_medium"],
            "utm_campaign": session["utm_campaign"],
            "referrer": session["referrer"],
            "channel": session["channel"],
            "device": session["device"],
            "os": session["os"],
            "user_agent": session["user_agent"],
            "country": session["country"],
            "ip_hash": session["ip_hash"],
            "landing_page": session["landing_page"],
            "is_bounce": session["is_bounce"],
            "started_at": session["started_at"],
            "ended_at": session.get("ended_at"),
            "metadata": {"source": config.SYNTHETIC_MARKER},
        })
        self.writer.write("sessions_by_anonymous", {
            "anonymous_id": session["anonymous_id"],
            "started_at": session["started_at"],
            "session_id": session["session_id"],
            "user_id": session["user_id"],
            "channel": session["channel"],
            "source": session["source"],
            "device": session["device"],
            "country": session["country"],
        })
        if session["user_id"]:
            self.writer.write("sessions_by_user", {
                "user_id": session["user_id"],
                "started_at": session["started_at"],
                "session_id": session["session_id"],
                "anonymous_id": session["anonymous_id"],
                "channel": session["channel"],
                "source": session["source"],
                "device": session["device"],
            })

    def _cart_item_row(self, cart_id, item, currency, added_at):
        return {
            "cart_id": cart_id,
            "variant_id": item["variant_id"],
            "product_id": item["product_id"],
            "product_name": item["product_name"],
            "variant_name": item["variant_name"],
            "attributes": item["attributes"],
            "quantity": item["quantity"],
            "unit_price": item["unit_price"],
            "unit_discounted_price": item["unit_discounted_price"],
            "line_total": item["line_total"],
            "currency": currency,
            "added_at": added_at,
        }

    def _cart_row(self, cart_id, session, user_id, items, totals, status, roll,
                  order_id, currency):
        return {
            "cart_id": cart_id,
            "session_id": session["session_id"],
            "anonymous_id": session["anonymous_id"],
            "user_id": user_id,
            "status": status,
            "currency": currency,
            "item_count": totals["item_count"],
            "subtotal": totals["subtotal"],
            "discount_pct": totals["discount_pct"],
            "discount_amount": totals["discount_amount"],
            "total": totals["total"],
            "lucky_roll_id": roll["roll_id"] if roll else None,
            "converted_order_id": order_id,
            "created_at": session["started_at"],
            "updated_at": session["started_at"] + timedelta(minutes=self.rng.randint(1, 30)),
            "metadata": {"source": config.SYNTHETIC_MARKER},
        }

    def _write_cart(self, cart_id, session, user_id, items, totals, status, roll,
                    order_id, currency, created_at):
        row = self._cart_row(cart_id, session, user_id, items, totals, status, roll,
                             order_id, currency)
        row["created_at"] = created_at
        self.writer.write("carts", row)
        self.writer.write_many("cart_items", [
            self._cart_item_row(cart_id, i, currency, created_at) for i in items
        ])
        self.writer.write("cart_by_session", {
            "session_id": session["session_id"],
            "cart_id": cart_id,
            "user_id": user_id,
            "status": status,
            "updated_at": row["updated_at"],
        })
        if user_id:
            self.writer.write("cart_by_user", {
                "user_id": user_id,
                "created_at": created_at,
                "cart_id": cart_id,
                "status": status,
                "total": totals["total"],
                "currency": currency,
            })
        if roll:
            self.writer.write("lucky_rolls", {
                "scope_type": roll["scope_type"],
                "scope_id": roll["scope_id"],
                "roll_date": roll["roll_date"],
                "rolled_value": roll["rolled_value"],
                "won": roll["won"],
                "discount_pct": roll["discount_pct"],
                "cart_id": roll["cart_id"],
                "created_at": roll["created_at"],
            })

    # ------------------------------------------------------------------
    # Metadata / summary
    # ------------------------------------------------------------------
    def _write_run_metadata(self) -> None:
        sessions = self.actuals["sessions"]
        converting = self.actuals["converting_sessions"]
        actual_conv = (Decimal(converting) / Decimal(sessions) * 100) if sessions else Decimal("0")
        self.writer.write("simulation_runs", {
            "run_id": self.run_id,
            "started_at": datetime.utcnow(),
            "finished_at": datetime.utcnow(),
            "status": "completed",
            "params": {
                "days": str(self.params.days),
                "users_per_day": f"{self.params.users_per_day[0]}-{self.params.users_per_day[1]}",
                "conversion_target_pct": str(self.params.conversion),
                "start_date": self.params.start_date.isoformat(),
                "seed": str(self.params.seed),
                "dirty": self.params.dirty,
            },
            "actuals": {
                "sessions": str(sessions),
                "orders": str(self.actuals["orders"]),
                "converting_sessions": str(converting),
                "conversion_pct": str(actual_conv.quantize(Decimal("0.001"))),
                "injected_issues": str(len(self.ledger.issues)),
            },
            "row_counts": {k: v for k, v in self.writer.counts.items()},
        })
        self.writer.write_positions("injected_issues", self.ledger.issues)

    def _summary(self) -> dict:
        sessions = self.actuals["sessions"]
        converting = self.actuals["converting_sessions"]
        actual_conv = (converting / sessions * 100) if sessions else 0.0
        return {
            "run_id": self.run_id,
            "sessions": sessions,
            "orders": self.actuals["orders"],
            "converting_sessions": converting,
            "target_conversion_pct": float(self.params.conversion),
            "actual_conversion_pct": round(actual_conv, 3),
            "injected_issues": len(self.ledger.issues),
            "issues_by_type": dict(self.ledger.by_type),
            "row_counts": self.writer.as_row_counts(),
        }

    def _weighted_sample_without_replacement(self, weights: list, k: int) -> set:
        """Pick k distinct indices weighted by `weights` (Efraimidis-Spirakis)."""
        keyed = []
        for index, weight in enumerate(weights):
            u = self.rng.random()
            key = u ** (1.0 / weight) if weight > 0 else 0.0
            keyed.append((key, index))
        keyed.sort(reverse=True)
        return {index for _key, index in keyed[:k]}

    @staticmethod
    def _weighted(rng: random.Random, weighted: tuple) -> str:
        values = [v for v, _ in weighted]
        weights = [w for _, w in weighted]
        return rng.choices(values, weights=weights, k=1)[0]
