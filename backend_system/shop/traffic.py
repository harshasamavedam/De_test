"""Traffic generation: sessions, attribution and raw funnel events.

Sessions carry the traffic `source`. Visitor identity is modelled with an
`anonymous_id` that persists across days (a returning cookie); when a visitor
logs in at checkout the anonymous id is stitched to a user via `identity_map`.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from . import config, ids
from .people import hash_ip

EVENT_TYPES = (
    "session_start",
    "page_view",
    "product_view",
    "add_to_cart",
    "cart_view",
    "lucky_check",
    "checkout_start",
    "login",
    "purchase",
    "session_end",
)

LANDING_PAGES = ("/", "/home", "/deals", "/new-arrivals", "/search", "/blog")


def _weighted_choice(rng: random.Random, weighted: tuple) -> str:
    values = [v for v, _ in weighted]
    weights = [w for _, w in weighted]
    return rng.choices(values, weights=weights, k=1)[0]


def _weighted_index(rng: random.Random, weights) -> int:
    return rng.choices(range(len(weights)), weights=weights, k=1)[0]


class TrafficFactory:
    """Generates sessions and the anonymous-id universe across all days."""

    def __init__(self, seed: int, ledger):
        self.seed = seed
        self.ledger = ledger
        self.rng = random.Random(f"traffic:{seed}")
        self.anon_counter = 0
        self.session_counter = 0
        # anonymous_id -> set of day offsets where it was seen
        self.anon_seen: dict[str, list] = {}

    def new_anonymous(self) -> str:
        self.anon_counter += 1
        return ids.anonymous_id(self.anon_counter)

    def attribution(self) -> dict:
        rng = self.rng
        channel = _weighted_choice(
            rng, tuple((c, s["weight"]) for c, s in config.CHANNELS.items())
        )
        utm_source = rng.choice(config.UTM_SOURCES[channel])
        source = f"{channel}" if not utm_source else f"{utm_source}/{channel}"
        return {
            "channel": channel,
            "source": source,
            "utm_source": utm_source,
            "utm_medium": config.UTM_MEDIUMS[channel],
            "utm_campaign": rng.choice(config.CAMPAIGNS),
            "referrer": rng.choice(("", "https://google.com", "https://reddit.com", "https://news.site")),
        }

    def make_session(
        self,
        day: date,
        seq: int,
        anonymous_id: str,
        user_id: str | None,
        started_at: datetime,
    ) -> dict:
        rng = self.rng
        device = _weighted_choice(rng, config.DEVICES)
        country = _weighted_choice(rng, config.COUNTRIES)
        attrs = self.attribution()
        channel_spec = config.CHANNELS[attrs["channel"]]

        duration_s = int(rng.lognormvariate(6.0, 0.8))
        duration_s = max(15, min(duration_s, 60 * 60 * 2))
        ended_at = started_at + timedelta(seconds=duration_s)

        # Some sessions are left open (data-quality: stale session).
        if self.ledger.chance("stale_session_open"):
            self.ledger.record(
                "sessions", "", "ended_at", "stale_session_open", ended_at, None
            )
            ended_at = None

        is_bounce = rng.random() < channel_spec["bounce"]
        session_id = ids.session_id(day, seq)

        return {
            "session_id": session_id,
            "anonymous_id": anonymous_id,
            "user_id": user_id,
            "source": attrs["source"],
            "utm_source": attrs["utm_source"],
            "utm_medium": attrs["utm_medium"],
            "utm_campaign": attrs["utm_campaign"],
            "referrer": attrs["referrer"],
            "channel": attrs["channel"],
            "device": device,
            "os": self._os(device, rng),
            "user_agent": rng.choice(config.USER_AGENTS[device]),
            "country": country,
            "ip_hash": hash_ip(f"10.{rng.randint(0,255)}.{rng.randint(0,255)}.{rng.randint(1,254)}"),
            "landing_page": rng.choice(LANDING_PAGES),
            "is_bounce": is_bounce,
            "started_at": started_at,
            "ended_at": ended_at,
            "duration_s": duration_s,
        }

    @staticmethod
    def _os(device: str, rng: random.Random) -> str:
        if device == "mobile":
            return "iOS" if rng.random() < 0.5 else "Android"
        if device == "tablet":
            return "iPadOS"
        return "Windows" if rng.random() < 0.6 else "macOS"

    def events_for(self, session: dict, outcome: dict) -> list[dict]:
        """Build the ordered event stream for a session.

        `outcome` describes what happened: views, cart, checkout, login, order.
        """
        rng = self.rng
        events: list[dict] = []
        t = session["started_at"]
        seq = 0

        def add(event_type, page=None, product_id=None, variant_id=None,
                cart_id=None, props=None):
            nonlocal seq, t
            seq += 1
            t = t + timedelta(seconds=rng.randint(3, 120))
            events.append(
                {
                    "event_id": ids.event_id(session["session_id"], seq),
                    "event_at": t,
                    "event_type": event_type,
                    "page": page,
                    "product_id": product_id,
                    "variant_id": variant_id,
                    "cart_id": cart_id,
                    "properties": props or {},
                    "session_id": session["session_id"],
                    "user_id": session["user_id"],
                    "anonymous_id": session["anonymous_id"],
                }
            )

        add("session_start", session["landing_page"])

        page_views = rng.randint(1, 6)
        for _ in range(page_views):
            add("page_view", session["landing_page"])

        for pv in outcome.get("product_views", []):
            add("product_view", "/product", pv["product_id"], pv["variant_id"])

        if outcome.get("cart_id"):
            for item in outcome.get("cart_items", []):
                add("add_to_cart", "/product", item["product_id"], item["variant_id"],
                    outcome["cart_id"], {"quantity": str(item["quantity"])})
            add("cart_view", "/cart", cart_id=outcome["cart_id"])

        if outcome.get("lucky_check"):
            roll = outcome["lucky_check"]
            add("lucky_check", "/cart", cart_id=outcome.get("cart_id"),
                props={"rolled": str(roll["rolled_value"]), "won": str(roll["won"])})

        if outcome.get("checkout"):
            add("checkout_start", "/checkout", cart_id=outcome.get("cart_id"))
        if outcome.get("logged_in"):
            add("login", "/login")
        if outcome.get("order_id"):
            add("purchase", "/order-confirmation",
                props={"order_id": outcome["order_id"]})

        # Temporal issue: occasionally emit an event after the session ended.
        if session["ended_at"] and events and self.ledger.chance("temporal_event_after_session"):
            late = events[-1].copy()
            late["event_id"] = late["event_id"] + "L"
            late["event_at"] = session["ended_at"] + timedelta(minutes=rng.randint(1, 60))
            self.ledger.record(
                "events", late["event_id"], "event_at",
                "temporal_event_after_session", session["ended_at"], late["event_at"],
            )
            events.append(late)

        add("session_end", session["landing_page"])
        return events
