"""Domain value objects for Bookinistic Studio 2.0.

Immutable, self-validating types with zero external dependencies (ADR-3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from backend.domain.exceptions import ValidationError

ARTICLE_REGEX = re.compile(r"^[A-Za-z0-9_-]{2,32}$")
ARTICLE_NUM_REGEX = re.compile(r"(\d+)")
STORE_BARCODE_PREFIX = "297847"


@dataclass(frozen=True)
class Article:
    """Immutable domain identifier for a book edition."""

    value: str

    def __post_init__(self) -> None:
        normalized = str(self.value or "").strip().upper()
        if not ARTICLE_REGEX.match(normalized):
            raise ValidationError(
                f"Invalid article '{self.value}': must match pattern ^[A-Za-z0-9_-]{{2,32}}$"
            )
        object.__setattr__(self, "value", normalized)

    @property
    def number(self) -> Optional[int]:
        """Extract numeric sequence number from article if present."""
        match = ARTICLE_NUM_REGEX.search(self.value)
        return int(match.group(1)) if match else None

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Isbn:
    """Validated International Standard Book Number (ISBN-10 or ISBN-13)."""

    value: str
    clean_digits: str
    is_valid: bool

    @classmethod
    def parse(cls, raw: Optional[str]) -> Optional["Isbn"]:
        """Parse, clean, and validate raw ISBN string."""
        if not raw or not str(raw).strip():
            return None

        cleaned = cls.clean(raw)
        if not cleaned:
            return None

        is_valid = cls._validate_checksum(cleaned) and not cls._is_placeholder(cleaned)
        return cls(value=str(raw).strip(), clean_digits=cleaned, is_valid=is_valid)

    @staticmethod
    def clean(raw: Optional[str]) -> str:
        """Strip hyphens, spaces, and formatting, returning uppercase alphanumeric digits."""
        if not raw:
            return ""
        return re.sub(r"[^\dX]", "", str(raw).upper())


    @staticmethod
    def _is_placeholder(clean: str) -> bool:
        """Reject obvious fake or test placeholder ISBNs like 978-5-0000-0000-0."""
        # Check for all same characters
        if len(set(clean)) <= 2:
            return True

        # Check for 0000000000 or 9780000000000
        if clean in ("0000000000", "9780000000000", "9790000000000"):
            return True

        # Check for trailing zeros block (e.g. 978-5-0000-0000-0 -> 9785000000000)
        digits_only = re.sub(r"\D", "", clean)
        if len(digits_only) == 13:
            body = digits_only[4:12]  # publisher + title block
            if body == "00000000":
                return True

        return False

    @classmethod
    def _validate_checksum(cls, clean: str) -> bool:
        """Validate ISBN-10 or ISBN-13 checksum."""
        # ISBN-10
        if len(clean) == 10 and re.match(r"^\d{9}[\dX]$", clean):
            total = 0
            for i, char in enumerate(clean):
                weight = 10 - i
                digit = 10 if char == "X" else int(char)
                total += weight * digit
            return total % 11 == 0

        # ISBN-13
        if len(clean) == 13 and clean.isdigit() and (clean.startswith("978") or clean.startswith("979")):
            total = sum(
                int(digit) * (1 if i % 2 == 0 else 3)
                for i, digit in enumerate(clean)
            )
            return total % 10 == 0

        return False

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Ean13:
    """GS1 EAN-13 barcode with store-specific prefix support."""

    value: str

    def __post_init__(self) -> None:
        clean = re.sub(r"\D", "", str(self.value or ""))
        if len(clean) != 13:
            raise ValidationError(f"Invalid EAN-13 length: expected 13 digits, got '{self.value}'")
        if not self.validate_checksum(clean):
            raise ValidationError(f"Invalid EAN-13 checksum for '{clean}'")
        object.__setattr__(self, "value", clean)

    @classmethod
    def calculate_check_digit(cls, first12: str) -> int:
        """Calculate EAN-13 check digit for a 12-digit string."""
        digits = [int(c) for c in str(first12) if c.isdigit()]
        if len(digits) != 12:
            return 0
        s_odd = sum(digits[i] for i in range(0, 12, 2))
        s_even = sum(digits[i] for i in range(1, 12, 2))
        total = s_odd + s_even * 3
        return (10 - (total % 10)) % 10

    @classmethod
    def validate_checksum(cls, digits13: str) -> bool:
        """Verify checksum of 13-digit EAN-13 string."""
        if len(digits13) != 13 or not digits13.isdigit():
            return False
        expected = cls.calculate_check_digit(digits13[:12])
        return int(digits13[12]) == expected

    @classmethod
    def from_article(cls, article_str: str, prefix: str = STORE_BARCODE_PREFIX) -> "Ean13":
        """Generate a valid, deterministic EAN-13 barcode from any article string."""
        raw_digits = re.sub(r"\D", "", str(article_str or ""))
        try:
            num = int(raw_digits)
            if num <= 0:
                num = 1
        except (ValueError, TypeError):
            num = 1

        prefix_clean = re.sub(r"\D", "", prefix)[:6].ljust(6, "0")
        base12 = f"{prefix_clean}{num:06d}"[-12:]
        check = cls.calculate_check_digit(base12)
        return cls(f"{base12}{check}")

    def __str__(self) -> str:
        return self.value


def _safe_int_or_none(val: Any) -> Optional[int]:
    """Parse string or float numbers like '130.5' to int without crashing."""
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


@dataclass(frozen=True)
class Dimensions:
    """Physical dimensions and weight of a book exemplar in millimeters and grams."""

    width_mm: int = 130
    length_mm: int = 205
    height_mm: int = 15
    weight_g: int = 250
    book_format_code: str = ""

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "Dimensions":
        """Safely parse dimensions from dictionary handling strings, floats, and empty values."""
        if not isinstance(data, dict):
            return cls()

        width = _safe_int_or_none(data.get("width") or data.get("width_mm"))
        length = _safe_int_or_none(data.get("length") or data.get("length_mm"))
        height = _safe_int_or_none(data.get("height") or data.get("height_mm"))
        wt = _safe_int_or_none(data.get("weight") or data.get("weight_g"))

        return cls(
            width_mm=width if width is not None and width > 0 else 130,
            length_mm=length if length is not None and length > 0 else 205,
            height_mm=height if height is not None and height > 0 else 15,
            weight_g=wt if wt is not None and wt > 0 else 250,
            book_format_code=str(data.get("book_format_code") or "").strip(),
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary suitable for JSON serialization and legacy schemas."""
        return {
            "width": self.width_mm,
            "length": self.length_mm,
            "height": self.height_mm,
            "weight": self.weight_g,
            "width_mm": self.width_mm,
            "length_mm": self.length_mm,
            "height_mm": self.height_mm,
            "weight_g": self.weight_g,
            "book_format_code": self.book_format_code,
        }


@dataclass(frozen=True)
class Price:
    """Monetary price value object in Russian Rubles."""

    amount: float

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValidationError("Price cannot be negative")
        object.__setattr__(self, "amount", round(float(self.amount), 2))

    @classmethod
    def parse(cls, raw: Union[str, int, float, None], default: float = 0.0) -> "Price":
        """Parse raw price string or number safely."""
        if raw is None:
            return cls(default)
        s = re.sub(r"[^\d.,]", "", str(raw)).replace(",", ".")
        try:
            val = float(s)
            return cls(max(0.0, val))
        except (ValueError, TypeError):
            return cls(default)

    def __str__(self) -> str:
        return f"{int(self.amount)} ₽" if self.amount.is_integer() else f"{self.amount:.2f} ₽"
