"""Payment-attempt generation.

An order can have several payment attempts: a failed attempt is followed by a
retry until it succeeds or attempts run out. Refunds and cancellations are
derived from order outcome.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP

from . import config

PAYMENT_COMPLETED = "completed"
PAYMENT_PROCESSING = "processing"
PAYMENT_FAILED = "failed"
PAYMENT_REFUNDED = "refunded"

FAILURE_REASONS = (
    "insufficient_funds",
    "card_declined",
    "gateway_timeout",
    "do_not_honor",
    "expired_card",
)


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _weighted_choice(rng: random.Random, weighted: tuple) -> str:
    values = [v for v, _ in weighted]
    weights = [w for _, w in weighted]
    return rng.choices(values, weights=weights, k=1)[0]


class PaymentFactory:
    def __init__(self, seed: int, ledger):
        self.seed = seed
        self.ledger = ledger
        self.rng = random.Random(f"payment:{seed}")
        self.counter = 0

    def next_payment_id(self, day) -> str:
        self.counter += 1
        return f"pay_{day:%Y%m%d}_{self.counter:07d}"

    def simulate_attempts(
        self,
        order_id: str,
        user_id: str,
        amount: Decimal,
        currency: str,
        order_status: str,
        created_at: datetime,
        day,
    ) -> list[dict]:
        """Return the list of payment attempts for an order."""
        rng = self.rng
        method = _weighted_choice(rng, config.PAYMENT_METHODS)
        gateway = rng.choice(config.GATEWAYS)
        attempts: list[dict] = []
        attempt_no = 0
        t = created_at

        # Cancelled orders may not get a successful payment at all.
        if order_status == "cancelled":
            attempt_no += 1
            attempts.append(
                self._attempt(
                    day, order_id, user_id, attempt_no, amount, currency, method,
                    gateway, "failed", t, failure_reason="order_cancelled",
                )
            )
            return attempts

        succeeded = False
        while attempt_no < config.MAX_PAYMENT_ATTEMPTS:
            attempt_no += 1
            t = t + timedelta(seconds=rng.randint(2, 45))
            if rng.random() < config.PAYMENT_SUCCESS_RATE:
                succeeded = True
                status = "refunded" if order_status == "refunded" else "completed"
                attempts.append(
                    self._attempt(
                        day, order_id, user_id, attempt_no, amount, currency,
                        method, gateway, status, t,
                    )
                )
                break
            attempts.append(
                self._attempt(
                    day, order_id, user_id, attempt_no, amount, currency, method,
                    gateway, "failed", t,
                    failure_reason=rng.choice(FAILURE_REASONS),
                )
            )

        # Duplicate payment issue: emit an extra identical attempt row.
        if self.ledger.chance("duplicate_payment") and attempts:
            dup = dict(attempts[-1])
            dup["payment_id"] = dup["payment_id"] + "D"
            self.ledger.record(
                "payments", dup["payment_id"], "payment_id",
                "duplicate_payment", attempts[-1]["payment_id"], dup["payment_id"],
            )
            attempts.append(dup)
        return attempts

    def _attempt(
        self,
        day,
        order_id: str,
        user_id: str,
        attempt_no: int,
        amount: Decimal,
        currency: str,
        method: str,
        gateway: str,
        status: str,
        t: datetime,
        failure_reason: str | None = None,
    ) -> dict:
        payment_id = self.next_payment_id(day)
        fee = _money(amount * config.GATEWAY_FEE_RATE + config.GATEWAY_FEE_FLAT)
        return {
            "payment_id": payment_id,
            "order_id": order_id,
            "user_id": user_id,
            "attempt_no": attempt_no,
            "amount": amount,
            "currency": currency,
            "method": method,
            "status": status,
            "gateway": gateway,
            "gateway_transaction_ref": f"txn_{payment_id}",
            "gateway_fee": fee,
            "failure_reason": failure_reason,
            "created_at": t,
            "processed_at": t if status != "processing" else None,
            "completed_at": t if status in ("completed", "refunded") else None,
            "failed_at": t if status == "failed" else None,
            "refunded_at": t + timedelta(days=2) if status == "refunded" else None,
        }
