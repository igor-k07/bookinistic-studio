"""SQLite implementation of ReferenceRepository for brands and dictionaries.

Fast autocomplete and lookup without full-table JSON scans.
Uses indexed normalized lowercase representation for fast Cyrillic matching.
"""

from __future__ import annotations

from typing import List

from backend.domain.ports import IReferenceRepository
from backend.infrastructure.persistence.sqlite_uow import SqliteUnitOfWork


class SqliteReferenceRepository(IReferenceRepository):
    """SQLite repository for reference brands and publisher dictionaries."""

    def __init__(self, uow: SqliteUnitOfWork) -> None:
        self.uow = uow

    def search_brands(self, query: str, limit: int = 20) -> List[str]:
        """Search reference brands with prefix priority."""
        q = (query or "").strip().lower()
        with self.uow:
            if not q:
                cursor = self.uow.execute(
                    "SELECT name FROM reference_brands ORDER BY name ASC LIMIT ?;",
                    (limit,),
                )
                return [row["name"] for row in cursor.fetchall()]

            prefix_param = f"{q}%"
            contains_param = f"%{q}%"

            # Prioritize exact prefix match, then substring match
            sql = """
                SELECT name FROM reference_brands
                WHERE name_normalized LIKE ?
                ORDER BY
                    CASE WHEN name_normalized LIKE ? THEN 0 ELSE 1 END,
                    length(name) ASC,
                    name ASC
                LIMIT ?;
            """
            cursor = self.uow.execute(sql, (contains_param, prefix_param, limit))
            return [row["name"] for row in cursor.fetchall()]

    def is_known_brand(self, brand: str) -> bool:
        """Check if brand is registered in verified Ozon brands table."""
        b = (brand or "").strip().lower()
        if not b:
            return False
        with self.uow:
            cursor = self.uow.execute(
                "SELECT 1 FROM reference_brands WHERE name_normalized = ?;",
                (b,),
            )
            return cursor.fetchone() is not None

    def add_brand(self, brand: str) -> None:
        """Register a new brand in reference table."""
        b = (brand or "").strip()
        if b:
            with self.uow:
                self.uow.execute(
                    "INSERT OR IGNORE INTO reference_brands (name, name_normalized) VALUES (?, ?);",
                    (b, b.lower()),
                )
