"""Business logic for the shop API.

Wires the HTTP layer to Cassandra via `ShopRepository`, applying the same
domain rules the simulator uses: no guest checkout, identity stitching at
login, frozen Lucky Check discounts, price-snapshotted order items and
multi-attempt payments.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from . import config
from .id_factory import IdFactory
from .orders import compute_order_totals
from .repository import ShopRepository


class ShopError(Exception):
    """Domain error carrying an HTTP status code."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class ShopService:
    def __init__(self, repository: ShopRepository, seed: int | None = None):
        self.repo = repository
        self.ids = IdFactory()
        self.rng = random.Random(seed)

    # ------------------------------------------------------------------
    # Traffic / sessions
    # ------------------------------------------------------------------
    def create_session(self, payload) -> dict:
        now = datetime.utcnow()
        anonymous_id = payload.anonymous_id or self.ids.new_anonymous()
        session_id = self.ids.new_session(now.date())

        channel = payload.channel or self._channel_from(payload)
        session = {
            "session_id": session_id,
            "anonymous_id": anonymous_id,
            "user_id": None,
            "source": payload.source or channel,
            "utm_source": payload.utm_source,
            "utm_medium": payload.utm_medium,
            "utm_campaign": payload.utm_campaign,
            "referrer": payload.referrer,
            "channel": channel,
            "device": payload.device,
            "os": None,
            "user_agent": None,
            "country": payload.country,
            "ip_hash": None,
            "landing_page": payload.landing_page,
            "is_bounce": False,
            "started_at": now,
            "ended_at": None,
            "metadata": {"origin": "api"},
        }
        self.repo.insert("sessions", session)
        self.repo.insert("sessions_by_anonymous", {
            "anonymous_id": anonymous_id,
            "started_at": now,
            "session_id": session_id,
            "user_id": None,
            "channel": channel,
            "source": session["source"],
            "device": payload.device,
            "country": payload.country,
        })
        return session

    def get_session(self, session_id: str) -> dict:
        session = self.repo.get_session(session_id)
        if not session:
            raise ShopError(f"session {session_id} not found", 404)
        return session

    def login(self, session_id: str, payload) -> dict:
        """Log in (or register) at checkout and stitch anonymous_id -> user_id."""
        session = self.get_session(session_id)
        email = payload.email.strip().lower()
        user_id = self.repo.get_user_id_by_email(email)
        # guard against a dangling email index pointing at a missing user
        if user_id and not self.repo.get_user(user_id):
            user_id = None
        now = datetime.utcnow()

        if user_id is None:
            if not payload.auto_register:
                raise ShopError(f"no user for email {email}", 404)
            user_id = self.ids.new_user()
            self.repo.insert("users", {
                "user_id": user_id,
                "email": email,
                "first_name": payload.first_name or "",
                "last_name": payload.last_name or "",
                "phone": None,
                "date_of_birth": None,
                "country": session.get("country"),
                "is_active": True,
                "created_at": now,
                "metadata": {"origin": "api"},
            })
            self.repo.insert("users_by_email", {
                "email": email, "user_id": user_id, "created_at": now,
            })

        # stitch and attach to session
        self.repo.insert("identity_map", {
            "anonymous_id": session["anonymous_id"],
            "user_id": user_id,
            "first_seen": session["started_at"],
            "linked_at": now,
            "link_source": "checkout_login",
        })
        self.repo.insert("identity_map_by_user", {
            "user_id": user_id,
            "anonymous_id": session["anonymous_id"],
            "first_seen": session["started_at"],
            "linked_at": now,
        })
        self.repo.update("session_user", (user_id, session_id))
        self.repo.insert("sessions_by_user", {
            "user_id": user_id,
            "started_at": session["started_at"],
            "session_id": session_id,
            "anonymous_id": session["anonymous_id"],
            "channel": session.get("channel"),
            "source": session.get("source"),
            "device": session.get("device"),
        })

        # adopt any active cart owned by this session
        cart_ref = self.repo.get_cart_by_session(session_id)
        if cart_ref:
            cart = self.repo.get_cart(cart_ref["cart_id"])
            if cart and cart["status"] == "active":
                self._write_cart(cart["cart_id"], session_id, session["anonymous_id"],
                                 user_id, cart, self.repo.get_cart_items(cart["cart_id"]))
        return {"user_id": user_id, "anonymous_id": session["anonymous_id"],
                "linked_at": now}

    # ------------------------------------------------------------------
    # Cart
    # ------------------------------------------------------------------
    def create_cart(self, payload) -> dict:
        session = self.get_session(payload.session_id)
        now = datetime.utcnow()
        existing = self.repo.get_cart_by_session(payload.session_id)
        if existing and (self.repo.get_cart(existing["cart_id"]) or {}).get("status") == "active":
            raise ShopError("session already has an active cart", 409)

        cart_id = self.ids.new_cart(now.date())
        cart = self._empty_cart(cart_id, session, payload.currency, now)
        self.repo.insert("carts", cart)
        self.repo.insert("cart_by_session", {
            "session_id": payload.session_id,
            "cart_id": cart_id,
            "user_id": session.get("user_id"),
            "status": "active",
            "updated_at": now,
        })
        return cart

    def get_cart(self, cart_id: str) -> dict:
        cart = self.repo.get_cart(cart_id)
        if not cart:
            raise ShopError(f"cart {cart_id} not found", 404)
        items = self.repo.get_cart_items(cart_id)
        cart = dict(cart)
        cart["items"] = items
        return cart

    def add_cart_item(self, cart_id: str, payload) -> dict:
        cart = self.repo.get_cart(cart_id)
        if not cart:
            raise ShopError(f"cart {cart_id} not found", 404)
        if cart["status"] != "active":
            raise ShopError(f"cart {cart_id} is not active", 409)

        variant = self.repo.get_variant(payload.variant_id)
        if not variant:
            raise ShopError(f"variant {payload.variant_id} not found", 404)

        currency = cart["currency"] or "USD"
        rate = config.CURRENCY_RATES_FROM_USD.get(currency, Decimal("1.00"))
        unit_price = _money(variant["price"] * rate)
        unit_discounted = _money(variant["discounted_price"] * rate)
        line_total = _money(unit_discounted * payload.quantity)

        self.repo.insert("cart_items", {
            "cart_id": cart_id,
            "variant_id": variant["variant_id"],
            "product_id": variant["product_id"],
            "product_name": variant["product_name"],
            "variant_name": variant["variant_name"],
            "attributes": variant["attributes"],
            "quantity": payload.quantity,
            "unit_price": unit_price,
            "unit_discounted_price": unit_discounted,
            "line_total": line_total,
            "currency": currency,
            "added_at": datetime.utcnow(),
        })
        self._recompute_cart(cart_id, session_id=cart["session_id"])
        return self.get_cart(cart_id)

    def remove_cart_item(self, cart_id: str, variant_id: str) -> dict:
        cart = self.repo.get_cart(cart_id)
        if not cart:
            raise ShopError(f"cart {cart_id} not found", 404)
        self.repo.delete_cart_item(cart_id, variant_id)
        self._recompute_cart(cart_id, session_id=cart["session_id"])
        return self.get_cart(cart_id)

    def lucky_check(self, cart_id: str) -> dict:
        cart = self.repo.get_cart(cart_id)
        if not cart:
            raise ShopError(f"cart {cart_id} not found", 404)
        if cart["status"] != "active":
            raise ShopError("lucky check is only available on an active cart", 409)

        session = self.repo.get_session(cart["session_id"]) or {}
        user_id = cart.get("user_id") or session.get("user_id")
        scope_type = config.LUCKY_SCOPE_USER if user_id else config.LUCKY_SCOPE_ANON
        scope_id = user_id or cart["anonymous_id"]
        today = date.today()

        if self.repo.get_lucky_roll(scope_type, scope_id, today):
            raise ShopError("lucky check already used today", 409)

        rolled = self.rng.randint(config.LUCKY_ROLL_MIN, config.LUCKY_ROLL_MAX)
        won = rolled in config.LUCKY_WINNING_VALUES
        discount_pct = config.LUCKY_DISCOUNT_PCT if won else Decimal("0")
        roll_id = f"roll_{scope_type}_{scope_id}_{today:%Y%m%d}"
        now = datetime.utcnow()

        self.repo.insert("lucky_rolls", {
            "scope_type": scope_type,
            "scope_id": scope_id,
            "roll_date": today,
            "rolled_value": rolled,
            "won": won,
            "discount_pct": discount_pct,
            "cart_id": cart_id,
            "created_at": now,
        })

        # freeze the roll id onto the cart; apply discount only on a win
        self._recompute_cart(
            cart_id, session_id=cart["session_id"],
            discount_pct=discount_pct if won else cart["discount_pct"],
            lucky_roll_id=roll_id,
        )

        message = (
            f"You won {discount_pct}% off!" if won else "No luck this time. Try again tomorrow."
        )
        return {
            "roll_id": roll_id,
            "scope_type": scope_type,
            "scope_id": scope_id,
            "roll_date": today,
            "rolled_value": rolled,
            "won": won,
            "discount_pct": discount_pct,
            "cart_id": cart_id,
            "message": message,
        }

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------
    def create_order(self, payload) -> dict:
        cart = self.repo.get_cart(payload.cart_id)
        if not cart:
            raise ShopError(f"cart {payload.cart_id} not found", 404)
        if cart["status"] != "active":
            raise ShopError("cart has already been converted or abandoned", 409)

        session = self.repo.get_session(cart["session_id"]) or {}
        user_id = cart.get("user_id") or session.get("user_id")
        if not user_id:
            # no guest checkout: caller must log in first
            raise ShopError("login required before checkout", 401)

        items = self.repo.get_cart_items(payload.cart_id)
        if not items:
            raise ShopError("cannot create an order from an empty cart", 400)

        now = datetime.utcnow()
        currency = cart["currency"] or "USD"
        order_id = self.ids.new_order(now.date())
        discount_pct = cart["discount_pct"] or Decimal("0")

        order_items = [self._snapshot_item(order_id, item, currency) for item in items]
        totals = compute_order_totals(order_items, discount_pct, order_id=order_id)

        user = self.repo.get_user(user_id) or {}
        addresses = self.repo.list_addresses(user_id)
        shipping = self._address_snapshot(user, addresses)

        order = {
            "order_id": order_id,
            "user_id": user_id,
            "cart_id": payload.cart_id,
            "session_id": cart["session_id"],
            "anonymous_id": cart["anonymous_id"],
            "source": session.get("source"),
            "channel": session.get("channel"),
            "status": "pending",
            "currency": currency,
            "item_count": totals["item_count"],
            "subtotal": totals["subtotal"],
            "discount_pct": totals["discount_pct"],
            "discount_amount": totals["discount_amount"],
            "discount_reason": "lucky_check" if discount_pct > 0 else "",
            "tax_amount": totals["tax_amount"],
            "shipping_amount": totals["shipping_amount"],
            "total_amount": totals["total_amount"],
            "shipping_address": shipping,
            "created_at": now,
            "updated_at": now,
        }
        self.repo.insert("orders", order)
        self.repo.insert("orders_by_user", {
            "user_id": user_id,
            "created_at": now,
            "order_id": order_id,
            "status": "pending",
            "total_amount": totals["total_amount"],
            "currency": currency,
            "item_count": totals["item_count"],
        })
        self.repo.insert_many("order_items", order_items)

        # mark cart converted and link the order
        self._recompute_cart(payload.cart_id, session_id=cart["session_id"],
                             status="converted", converted_order_id=order_id)

        order = dict(order)
        order["items"] = order_items
        return order

    def get_order(self, order_id: str) -> dict:
        order = self.repo.get_order(order_id)
        if not order:
            raise ShopError(f"order {order_id} not found", 404)
        order = dict(order)
        order["items"] = self.repo.get_order_items(order_id)
        return order

    def list_user_orders(self, user_id: str) -> list[dict]:
        if not self.repo.get_user(user_id):
            raise ShopError(f"user {user_id} not found", 404)
        return self.repo.get_orders_by_user(user_id)

    # ------------------------------------------------------------------
    # Payments
    # ------------------------------------------------------------------
    def create_payment(self, payload) -> dict:
        order = self.repo.get_order(payload.order_id)
        if not order:
            raise ShopError(f"order {payload.order_id} not found", 404)

        existing = self.repo.get_payments_by_order(payload.order_id)
        attempt_no = max((p["attempt_no"] for p in existing), default=0) + 1
        if attempt_no > config.MAX_PAYMENT_ATTEMPTS:
            raise ShopError("maximum payment attempts reached", 409)

        now = datetime.utcnow()
        payment_id = self.ids.new_payment(now.date())
        fee = _money(order["total_amount"] * config.GATEWAY_FEE_RATE + config.GATEWAY_FEE_FLAT)
        payment = {
            "payment_id": payment_id,
            "order_id": payload.order_id,
            "user_id": order["user_id"],
            "attempt_no": attempt_no,
            "amount": order["total_amount"],
            "currency": order["currency"],
            "method": payload.method,
            "status": "pending",
            "gateway": payload.gateway,
            "gateway_transaction_ref": f"txn_{payment_id}",
            "gateway_fee": fee,
            "failure_reason": None,
            "created_at": now,
            "processed_at": None,
            "completed_at": None,
            "failed_at": None,
            "refunded_at": None,
            "metadata": {"origin": "api"},
        }
        self.repo.insert("payments", payment)
        self.repo.insert("payments_by_order", {
            "order_id": payload.order_id,
            "attempt_no": attempt_no,
            "payment_id": payment_id,
            "status": "pending",
            "amount": payment["amount"],
            "currency": payment["currency"],
            "method": payment["method"],
            "gateway": payment["gateway"],
            "created_at": now,
            "completed_at": None,
            "failed_at": None,
        })
        return payment

    def get_payment(self, payment_id: str) -> dict:
        payment = self.repo.get_payment(payment_id)
        if not payment:
            raise ShopError(f"payment {payment_id} not found", 404)
        return payment

    def process_payment(self, payment_id: str) -> dict:
        payment = self.get_payment(payment_id)
        if payment["status"] != "pending":
            raise ShopError(f"payment is {payment['status']}, cannot process", 409)
        now = datetime.utcnow()
        self.repo.update("payment_status", (
            "processing", now, None, None, None, None, payment_id,
        ))
        self.repo.update("payment_status_by_order", (
            "processing", None, None, payment["order_id"], payment["attempt_no"],
        ))
        return self.get_payment(payment_id)

    def complete_payment(self, payment_id: str, transaction_reference: str | None = None) -> dict:
        payment = self.get_payment(payment_id)
        if payment["status"] not in ("pending", "processing"):
            raise ShopError(f"payment is {payment['status']}, cannot complete", 409)
        now = datetime.utcnow()
        self.repo.update("payment_status", (
            "completed", now, now, None, None, None, payment_id,
        ))
        self.repo.update("payment_status_by_order", (
            "completed", now, None, payment["order_id"], payment["attempt_no"],
        ))
        self._set_order_status(payment["order_id"], "completed")
        return self.get_payment(payment_id)

    def fail_payment(self, payment_id: str, failure_reason: str | None = None) -> dict:
        payment = self.get_payment(payment_id)
        if payment["status"] not in ("pending", "processing"):
            raise ShopError(f"payment is {payment['status']}, cannot fail", 409)
        now = datetime.utcnow()
        self.repo.update("payment_status", (
            "failed", now, None, now, None, failure_reason or "card_declined", payment_id,
        ))
        self.repo.update("payment_status_by_order", (
            "failed", None, now, payment["order_id"], payment["attempt_no"],
        ))
        return self.get_payment(payment_id)

    def refund_payment(self, payment_id: str) -> dict:
        payment = self.get_payment(payment_id)
        if payment["status"] != "completed":
            raise ShopError("only completed payments can be refunded", 409)
        now = datetime.utcnow()
        self.repo.update("payment_status", (
            "refunded", payment["processed_at"], payment["completed_at"], None, now,
            None, payment_id,
        ))
        self.repo.update("payment_status_by_order", (
            "refunded", payment["completed_at"], None, payment["order_id"],
            payment["attempt_no"],
        ))
        self._set_order_status(payment["order_id"], "refunded")
        return self.get_payment(payment_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _set_order_status(self, order_id: str, status: str) -> None:
        now = datetime.utcnow()
        self.repo.update("order_status", (status, now, order_id))
        row = self.repo.one(
            "SELECT user_id, created_at FROM orders WHERE order_id = %s", (order_id,)
        )
        if row:
            self.repo.update("order_status_by_user", (
                status, row["user_id"], row["created_at"], order_id,
            ))

    def _recompute_cart(self, cart_id, session_id, status=None, discount_pct=None,
                        lucky_roll_id=None, converted_order_id=None):
        cart = self.repo.get_cart(cart_id)
        if not cart:
            raise ShopError(f"cart {cart_id} not found", 404)
        items = self.repo.get_cart_items(cart_id)
        pct = discount_pct if discount_pct is not None else (cart["discount_pct"] or Decimal("0"))
        subtotal = _money(sum((i["line_total"] for i in items), Decimal("0")))
        discount_amount = _money(subtotal * pct / Decimal("100"))
        total = _money(subtotal - discount_amount)
        now = datetime.utcnow()
        new_status = status or cart["status"]
        roll_id = lucky_roll_id if lucky_roll_id is not None else cart["lucky_roll_id"]
        order_id = converted_order_id if converted_order_id is not None else cart["converted_order_id"]
        self.repo.update("cart_status", (
            new_status, len(items), subtotal, pct, discount_amount, total,
            roll_id, order_id, now, cart_id,
        ))
        self.repo.update("cart_session_status", (
            cart.get("user_id"), new_status, now, session_id,
        ))
        if cart.get("user_id"):
            self.repo.insert("cart_by_user", {
                "user_id": cart["user_id"],
                "created_at": cart["created_at"],
                "cart_id": cart_id,
                "status": new_status,
                "total": total,
                "currency": cart["currency"],
            })

    def _write_cart(self, cart_id, session_id, anonymous_id, user_id, cart, items):
        self.repo.insert("carts", {
            "cart_id": cart_id,
            "session_id": session_id,
            "anonymous_id": anonymous_id,
            "user_id": user_id,
            "status": cart["status"],
            "currency": cart["currency"],
            "item_count": cart["item_count"],
            "subtotal": cart["subtotal"],
            "discount_pct": cart["discount_pct"],
            "discount_amount": cart["discount_amount"],
            "total": cart["total"],
            "lucky_roll_id": cart["lucky_roll_id"],
            "converted_order_id": cart["converted_order_id"],
            "created_at": cart["created_at"],
            "updated_at": datetime.utcnow(),
            "metadata": cart.get("metadata"),
        })
        self.repo.update("cart_session_status", (user_id, cart["status"], datetime.utcnow(), session_id))

    def _empty_cart(self, cart_id, session, currency, now):
        return {
            "cart_id": cart_id,
            "session_id": session["session_id"],
            "anonymous_id": session["anonymous_id"],
            "user_id": session.get("user_id"),
            "status": "active",
            "currency": currency,
            "item_count": 0,
            "subtotal": Decimal("0.00"),
            "discount_pct": Decimal("0"),
            "discount_amount": Decimal("0.00"),
            "total": Decimal("0.00"),
            "lucky_roll_id": None,
            "converted_order_id": None,
            "created_at": now,
            "updated_at": now,
            "metadata": {"origin": "api"},
        }

    @staticmethod
    def _snapshot_item(order_id, item, currency):
        return {
            "order_id": order_id,
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
        }

    @staticmethod
    def _address_snapshot(user, addresses):
        if addresses:
            a = addresses[0]
            return {
                "full_name": a.get("full_name") or "",
                "line1": a.get("line1") or "",
                "city": a.get("city") or "",
                "region": a.get("region") or "",
                "postal_code": a.get("postal_code") or "",
                "country": a.get("country") or user.get("country") or "",
            }
        return {
            "full_name": f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
            "city": "", "region": "", "postal_code": "",
            "country": user.get("country") or "",
        }

    @staticmethod
    def _channel_from(payload) -> str:
        if payload.utm_medium in config.UTM_MEDIUMS.values():
            mapping = {v: k for k, v in config.UTM_MEDIUMS.items()}
            return mapping.get(payload.utm_medium, "direct")
        if payload.referrer:
            return "referral"
        return "direct"
