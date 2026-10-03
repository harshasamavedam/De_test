"""Static configuration for the shop simulator.

Everything tunable in one place: traffic sources, catalog shape, discount
rules, currencies and the data-quality issue rates.
"""

from decimal import Decimal

# ---------------------------------------------------------------------------
# Simulation defaults
# ---------------------------------------------------------------------------

DEFAULT_KEYSPACE = "shop"
DEFAULT_SEED = 42
DEFAULT_CONVERSION = Decimal("3.5")
DEFAULT_USERS_PER_DAY = (500, 2000)
DEFAULT_DAYS = 30
DEFAULT_DIRTY_PROFILE = "realistic"

# ---------------------------------------------------------------------------
# Time / volume shaping
# ---------------------------------------------------------------------------

# Multiplier applied by weekday (Monday=0 .. Sunday=6). Weekends are quieter.
WEEKDAY_VOLUME_WEIGHTS = (1.08, 1.10, 1.12, 1.10, 1.05, 0.88, 0.82)

# Mild growth so later days trend slightly busier than earlier ones.
DAILY_GROWTH_RATE = 0.006

# Relative likelihood of a session starting in each hour of the day.
HOUR_WEIGHTS = (
    1.2, 0.7, 0.4, 0.3, 0.3, 0.5, 1.0, 1.8, 3.0, 3.8, 4.2, 3.6,
    3.2, 3.9, 4.4, 4.0, 3.4, 3.0, 2.8, 3.1, 3.6, 3.2, 2.4, 1.7,
)

# ---------------------------------------------------------------------------
# Traffic sources
# ---------------------------------------------------------------------------

# channel -> (weight, conversion_multiplier, bounce_probability)
#
# `weight` is the share of sessions, `conversion_multiplier` scales order
# intent relative to the daily baseline, `bounce_probability` is the chance a
# session never views a product.
CHANNELS = {
    "organic": {"weight": 30, "conversion_multiplier": 1.05, "bounce": 0.42},
    "paid_social": {"weight": 24, "conversion_multiplier": 0.70, "bounce": 0.58},
    "direct": {"weight": 18, "conversion_multiplier": 1.35, "bounce": 0.28},
    "email": {"weight": 12, "conversion_multiplier": 1.55, "bounce": 0.25},
    "referral": {"weight": 10, "conversion_multiplier": 1.10, "bounce": 0.40},
    "affiliate": {"weight": 6, "conversion_multiplier": 0.95, "bounce": 0.45},
}

UTM_SOURCES = {
    "organic": ("google", "bing", "duckduckgo"),
    "paid_social": ("facebook", "instagram", "tiktok", "x"),
    "direct": ("",),
    "email": ("newsletter", "promo_mailer"),
    "referral": ("reddit", "youtube", "partner_blog"),
    "affiliate": ("cashkaro", "slickdeals"),
}

UTM_MEDIUMS = {
    "organic": "organic",
    "paid_social": "cpc",
    "direct": "(none)",
    "email": "email",
    "referral": "referral",
    "affiliate": "affiliate",
}

CAMPAIGNS = (
    "spring_sale",
    "welcome_offer",
    "retarget_q3",
    "flash_weekend",
    "loyalty_boost",
    "",
)

DEVICES = (("mobile", 62), ("desktop", 30), ("tablet", 8))

USER_AGENTS = {
    "mobile": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) Mobile/15E148",
        "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 Mobile Safari/537.36",
    ),
    "desktop": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5) Firefox/121.0",
    ),
    "tablet": (
        "Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) Mobile/15E148",
    ),
}

COUNTRIES = (
    ("US", 55),
    ("IN", 18),
    ("GB", 10),
    ("DE", 7),
    ("CA", 6),
    ("AU", 4),
)

# channel -> (country code weight overrides are intentionally omitted; global mix)
CURRENCY_BY_COUNTRY = {
    "US": "USD",
    "IN": "INR",
    "GB": "GBP",
    "DE": "EUR",
    "CA": "CAD",
    "AU": "AUD",
}

CURRENCY_RATES_FROM_USD = {
    "USD": Decimal("1.00"),
    "INR": Decimal("83.20"),
    "GBP": Decimal("0.79"),
    "EUR": Decimal("0.92"),
    "CAD": Decimal("1.36"),
    "AUD": Decimal("1.52"),
}

# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------

# category_id -> (display name, (product base names,), (brands,), extra tax rate)
CATEGORIES = {
    "electronics": {
        "name": "Electronics",
        "products": (
            "Wireless Earbuds", "Smart Speaker", "4K Monitor", "Mechanical Keyboard",
            "Portable SSD", "Webcam Pro",
        ),
        "brands": ("Apex", "Nexa", "VoltEdge", "Orbit"),
    },
    "clothing": {
        "name": "Clothing",
        "products": (
            "Performance Tee", "Classic Hoodie", "Trail Jacket", "Everyday Pants",
            "Athletic Shorts", "Canvas Cap",
        ),
        "brands": ("Northline", "Harbor", "Summit", "Luma"),
    },
    "home_kitchen": {
        "name": "Home & Kitchen",
        "products": (
            "Cookware Set", "Bottle Set", "Home Lamp", "Storage Bin",
            "Travel Mug", "Chef Knife",
        ),
        "brands": ("Hearth", "Terra", "Cascade", "Meridian"),
    },
    "sports_outdoors": {
        "name": "Sports & Outdoors",
        "products": (
            "Yoga Mat", "Trail Backpack", "Water Bottle", "Camp Stove",
            "Resistance Bands", "Cycling Helmet",
        ),
        "brands": ("Summit", "Trek", "Ridge", "Basecamp"),
    },
    "beauty": {
        "name": "Beauty",
        "products": (
            "Face Serum", "Lip Balm", "Hair Oil", "Sunscreen SPF50",
            "Body Lotion", "Perfume",
        ),
        "brands": ("Glow", "Bloom", "Lumen", "Aura"),
    },
    "toys_games": {
        "name": "Toys & Games",
        "products": (
            "Building Blocks", "Board Game", "Puzzle 1000pc", "RC Car",
            "Plush Bear", "Card Deck",
        ),
        "brands": ("Playhaus", "Wonder", "Tinker", "Quest"),
    },
    "books": {
        "name": "Books",
        "products": (
            "Mystery Novel", "Cookbook", "Sci-Fi Anthology", "Self Help",
            "History Book", "Children Story",
        ),
        "brands": ("Inkwell", "Paperland", "Quill", "Storyline"),
    },
    "pet_supplies": {
        "name": "Pet Supplies",
        "products": (
            "Pet Feeder", "Chew Toy", "Cat Tree", "Dog Leash",
            "Aquarium Filter", "Pet Bed",
        ),
        "brands": ("Pawly", "Fetch", "Whisker", "Barkway"),
    },
}

VARIANT_ATTRIBUTES = {
    "electronics": (("color", ("Black", "White", "Silver")), ("warranty", ("1y", "2y"))),
    "clothing": (("color", ("Black", "Blue", "Red", "Gray")), ("size", ("S", "M", "L", "XL"))),
    "home_kitchen": (("color", ("White", "Gray", "Blue")), ("material", ("Steel", "Glass", "Bamboo"))),
    "sports_outdoors": (("color", ("Black", "Green", "Orange")), ("size", ("Standard", "Large"))),
    "beauty": (("volume", ("30ml", "50ml", "100ml")), ("type", ("Normal", "Sensitive"))),
    "toys_games": (("age", ("3+", "6+", "12+")), ("edition", ("Standard", "Deluxe"))),
    "books": (("format", ("Paperback", "Hardcover")), ("language", ("English", "Spanish"))),
    "pet_supplies": (("size", ("Small", "Medium", "Large")), ("color", ("Blue", "Pink", "Green"))),
}

# Price bands per category, in USD (min, max).
PRICE_BANDS_USD = {
    "electronics": (25, 900),
    "clothing": (12, 130),
    "home_kitchen": (10, 240),
    "sports_outdoors": (15, 300),
    "beauty": (6, 80),
    "toys_games": (8, 120),
    "books": (5, 45),
    "pet_supplies": (8, 150),
}

PRODUCTS_PER_BRAND = 3
VARIANTS_PER_PRODUCT = 3

# ---------------------------------------------------------------------------
# Cart / funnel shaping
# ---------------------------------------------------------------------------

# Probability a session creates at least one cart (before conversion logic).
CART_RATE = 0.30
# Probability a cart session adds a second item.
MULTI_ITEM_CART_RATE = 0.35
# Max distinct variants in one cart.
MAX_CART_ITEMS = 5
# Max quantity per line.
MAX_LINE_QUANTITY = 4

# Fraction of converting sessions that place a second order the same day.
RETURN_ORDER_RATE = 0.05

# ---------------------------------------------------------------------------
# Lucky check
# ---------------------------------------------------------------------------

LUCKY_ROLL_MIN = 1
LUCKY_ROLL_MAX = 1000
LUCKY_WINNING_VALUES = (7, 8, 9, 10)  # 0.4% win chance
LUCKY_DISCOUNT_PCT = Decimal("20")  # big prize for a rare win
LUCKY_SCOPE_USER = "user"
LUCKY_SCOPE_ANON = "anonymous"

# ---------------------------------------------------------------------------
# Payments
# ---------------------------------------------------------------------------

PAYMENT_METHODS = (
    ("credit_card", 55),
    ("paypal", 22),
    ("bank_transfer", 13),
    ("wallet", 10),
)

GATEWAYS = ("stripe", "adyen", "razorpay")

# First attempt succeeds with this probability; failures may be retried.
PAYMENT_SUCCESS_RATE = 0.90
MAX_PAYMENT_ATTEMPTS = 3
GATEWAY_FEE_RATE = Decimal("0.029")  # 2.9% + flat
GATEWAY_FEE_FLAT = Decimal("0.30")

# Probability an order is refunded after a completed payment.
REFUND_RATE = 0.04
# Probability an order is cancelled before payment completes.
CANCEL_RATE = 0.02

TAX_RATE = Decimal("0.08")
SHIPPING_FLAT = Decimal("6.99")
FREE_SHIPPING_THRESHOLD = Decimal("75.00")

# ---------------------------------------------------------------------------
# Data quality ("realistic" profile issue rates)
# ---------------------------------------------------------------------------

DIRTY_RATES = {
    "null_email": 0.04,
    "null_phone": 0.08,
    "format_email": 0.05,
    "format_country": 0.04,
    "trailing_space": 0.03,
    "referential_variant": 0.01,
    "temporal_event_after_session": 0.02,
    "financial_discounted_above": 0.01,
    "financial_negative_qty": 0.004,
    "financial_rounding": 0.01,
    "duplicate_payment": 0.015,
    "identity_shared_email": 0.01,
    "enum_casing": 0.02,
    "stale_session_open": 0.03,
    "stale_cart_idle": 0.02,
}

# Seed data is synthetically generated; this marker keeps it obviously fake.
SYNTHETIC_MARKER = "synthetic"
