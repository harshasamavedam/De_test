"""User, address and identity generation.

PII is clearly synthetic (example.com emails, reserved phone ranges, fictional
addresses) but structured realistically. Some quality issues are injected via
the shared ledger.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, timedelta

from . import config, ids

FIRST_NAMES = (
    "Avery", "Jordan", "Morgan", "Riley", "Casey", "Taylor", "Quinn", "Cameron",
    "Priya", "Arjun", "Wei", "Yuki", "Sofia", "Mateo", "Lena", "Omar",
    "Hannah", "Diego", "Nadia", "Ethan", "Chloe", "Ravi", "Mia", "Noah",
)
LAST_NAMES = (
    "Parker", "Reed", "Hayes", "Brooks", "Bennett", "Foster", "Rivera", "Patel",
    "Sharma", "Kim", "Nakamura", "Rossi", "Garcia", "Novak", "Ahmed", "Silva",
    "Walsh", "Costa", "Fischer", "Okafor",
)
STREET_NAMES = ("Maple", "Cedar", "Pine", "Lake", "Hill", "Oak", "Willow", "Park")
CITIES_BY_COUNTRY = {
    "US": (("Seattle", "WA", "98101"), ("Austin", "TX", "78701"), ("Denver", "CO", "80202")),
    "IN": (("Mumbai", "MH", "400001"), ("Bengaluru", "KA", "560001"), ("Delhi", "DL", "110001")),
    "GB": (("London", "ENG", "EC1A"), ("Manchester", "ENG", "M1")),
    "DE": (("Berlin", "BE", "10115"), ("Munich", "BY", "80331")),
    "CA": (("Toronto", "ON", "M5H"), ("Vancouver", "BC", "V6B")),
    "AU": (("Sydney", "NSW", "2000"), ("Melbourne", "VIC", "3000")),
}


def _weighted_choice(rng: random.Random, weighted: tuple) -> str:
    values = [v for v, _ in weighted]
    weights = [w for _, w in weighted]
    return rng.choices(values, weights=weights, k=1)[0]


def _email(first: str, last: str, n: int, rng: random.Random) -> str:
    domain = rng.choice(("example.com", "mail.example.com", "test.example.org"))
    style = rng.randint(0, 2)
    if style == 0:
        return f"{first.lower()}.{last.lower()}@{domain}"
    if style == 1:
        return f"{first.lower()}{n}@{domain}"
    return f"{first[0].lower()}{last.lower()}@example.com"


class PeopleFactory:
    """Creates users lazily and keeps an id<->email index for stitching."""

    def __init__(self, seed: int, ledger, catalog):
        self.seed = seed
        self.ledger = ledger
        self.catalog = catalog
        self.rng = random.Random(f"people:{seed}")
        self.users: list[dict] = []
        self.addresses: list[tuple] = []
        self.by_email: dict[str, str] = {}
        self._email_owner: dict[str, str] = {}

    def country_mix(self) -> str:
        return _weighted_choice(self.rng, config.COUNTRIES)

    def create_user(self, n: int, created_at: datetime) -> dict:
        first = self.rng.choice(FIRST_NAMES)
        last = self.rng.choice(LAST_NAMES)
        user_id = ids.user_id(n)
        country = self.country_mix()
        email = _email(first, last, n, self.rng)

        # identity issue: occasionally let two users share one email.
        if self.ledger.chance("identity_shared_email") and self._email_owner:
            email = self.rng.choice(list(self._email_owner))
            self.ledger.record(
                "users", user_id, "email", "identity_shared_email", None, email
            )

        email = self.ledger.email("users", user_id, email)
        phone = self.ledger.phone("users", user_id, self._phone(n))
        country_field = self.ledger.country("users", user_id, country)
        last = self.ledger.trailing_space("users", user_id, "last_name", last)

        user = {
            "user_id": user_id,
            "email": email,
            "first_name": first,
            "last_name": last,
            "phone": phone,
            "date_of_birth": self._dob(),
            "country": country_field,
            "is_active": True,
            "created_at": created_at,
            "metadata": {"source": config.SYNTHETIC_MARKER},
        }
        self.users.append(user)
        if email:
            self.by_email[email] = user_id
            self._email_owner.setdefault(email, user_id)
        return user

    def address_for(self, n: int, user: dict) -> tuple:
        country = user["country"] or "US"
        if country not in CITIES_BY_COUNTRY:
            country = "US"
        city, region, postal = self.rng.choice(CITIES_BY_COUNTRY[country])
        address_id = ids.address_id(n)
        record = (
            user["user_id"],
            address_id,
            self.rng.choice(("home", "work")),
            f"{user['first_name']} {user['last_name']}",
            f"{self.rng.randint(1, 9999)} {self.rng.choice(STREET_NAMES)} St",
            None,
            city,
            region,
            postal,
            country,
            user["phone"],
            True,
            user["created_at"],
        )
        self.addresses.append(record)
        return record

    # -- helpers -----------------------------------------------------------
    @staticmethod
    def _phone(n: int) -> str:
        return f"+1-202-555-{1000 + n % 9000:04d}"

    def _dob(self) -> date:
        year = self.rng.randint(1960, 2005)
        month = self.rng.randint(1, 12)
        day = self.rng.randint(1, 28)
        return date(year, month, day)


def hash_ip(ip: str) -> str:
    return hashlib.sha256(ip.encode()).hexdigest()[:16]


def fingerprint(anonymous_id: str) -> str:
    return hashlib.sha1(anonymous_id.encode()).hexdigest()[:12]
