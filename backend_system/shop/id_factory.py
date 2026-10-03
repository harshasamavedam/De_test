"""Runtime id generation for API-created entities.

Simulator ids are deterministic and batch-oriented; live API ids need to be
unique without coordination, so a short random suffix is appended.
"""

from __future__ import annotations

import secrets
from datetime import date


def _token() -> str:
    return secrets.token_hex(4)


class IdFactory:
    def new_user(self) -> str:
        return f"usr_{_token()}"

    def new_anonymous(self) -> str:
        return f"anon_{_token()}"

    def new_session(self, day: date) -> str:
        return f"sess_{day:%Y%m%d}_{_token()}"

    def new_cart(self, day: date) -> str:
        return f"cart_{day:%Y%m%d}_{_token()}"

    def new_order(self, day: date) -> str:
        return f"ord_{day:%Y%m%d}_{_token()}"

    def new_payment(self, day: date) -> str:
        return f"pay_{day:%Y%m%d}_{_token()}"
