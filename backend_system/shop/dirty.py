"""Intentional data-quality issue injection.

The `realistic` profile sprinkles common real-world defects into the generated
data. Every injected issue is written to an in-memory ledger (later persisted
to `injected_issues`) so the data team has a ground-truth answer key.
"""

from __future__ import annotations

import random
from datetime import datetime

from . import config


class IssueLedger:
    """Decides when to inject issues and records what was injected."""

    def __init__(self, run_id: str, seed: int, profile: str = "realistic"):
        self.run_id = run_id
        self.profile = profile
        self.rng = random.Random(f"dirty:{seed}")
        self.rates = dict(config.DIRTY_RATES)
        self.issues: list[tuple] = []
        self._issue_counter = 0
        self.by_type: dict[str, int] = {}

    def enabled(self) -> bool:
        return self.profile != "clean"

    def chance(self, issue_type: str) -> bool:
        """Return True with the configured rate for the issue type."""
        if not self.enabled():
            return False
        return self.rng.random() < self.rates.get(issue_type, 0.0)

    def record(
        self,
        table_name: str,
        entity_id: str,
        column_name: str,
        issue_type: str,
        original,
        injected,
    ) -> None:
        self._issue_counter += 1
        issue_id = f"iss_{self._issue_counter:08d}"
        self.issues.append(
            (
                self.run_id,
                issue_id,
                table_name,
                entity_id,
                column_name,
                issue_type,
                None if original is None else str(original),
                None if injected is None else str(injected),
                datetime.utcnow(),
            )
        )
        self.by_type[issue_type] = self.by_type.get(issue_type, 0) + 1

    # -- field helpers -----------------------------------------------------
    def email(self, table: str, entity_id: str, value: str | None):
        if self.chance("null_email"):
            self.record(table, entity_id, "email", "null_email", value, None)
            return None
        if value and self.chance("format_email"):
            broken = value.upper() if self.rng.random() < 0.5 else f"  {value} "
            self.record(table, entity_id, "email", "format_email", value, broken)
            return broken
        return value

    def phone(self, table: str, entity_id: str, value: str | None):
        if self.chance("null_phone"):
            self.record(table, entity_id, "phone", "null_phone", value, None)
            return None
        return value

    def country(self, table: str, entity_id: str, value: str | None):
        if value and self.chance("format_country"):
            broken = value.lower() if self.rng.random() < 0.5 else value.upper()
            self.record(table, entity_id, "country", "format_country", value, broken)
            return broken
        return value

    def trailing_space(self, table: str, entity_id: str, column: str, value):
        if isinstance(value, str) and self.chance("trailing_space"):
            broken = f"{value}  "
            self.record(table, entity_id, column, "trailing_space", value, broken)
            return broken
        return value

    def status_casing(self, table: str, entity_id: str, value: str | None):
        if value and self.chance("enum_casing"):
            broken = value.capitalize()
            self.record(table, entity_id, "status", "enum_casing", value, broken)
            return broken
        return value

    def currency_casing(self, table: str, entity_id: str, value: str | None):
        if value and self.chance("enum_casing"):
            broken = value.lower()
            self.record(table, entity_id, "currency", "enum_casing", value, broken)
            return broken
        return value
