"""Unit tests for domain value objects, enums, and exceptions (Step 1.3)."""

import pytest

from backend.domain.enums import (
    AssetStatus,
    BookCondition,
    BookEra,
    FieldSource,
    OzonSyncStatus,
    PhotoRole,
)
from backend.domain.exceptions import ValidationError
from backend.domain.value_objects import (
    Article,
    Dimensions,
    Ean13,
    Isbn,
    Price,
)


class TestArticleValueObject:
    def test_valid_articles(self) -> None:
        art = Article("dp-b-10005")
        assert art.value == "DP-B-10005"
        assert art.number == 10005
        assert str(art) == "DP-B-10005"

        art2 = Article("BOOK_999")
        assert art2.value == "BOOK_999"
        assert art2.number == 999

    def test_invalid_articles_raise(self) -> None:
        with pytest.raises(ValidationError):
            Article("")
        with pytest.raises(ValidationError):
            Article("A")  # Too short (< 2 chars)
        with pytest.raises(ValidationError):
            Article("article with spaces")
        with pytest.raises(ValidationError):
            Article("art/slash")


class TestIsbnValueObject:
    def test_valid_isbn10_numeric_and_x(self) -> None:
        # 0-306-40615-2 (valid ISBN-10)
        isbn1 = Isbn.parse("0-306-40615-2")
        assert isbn1 is not None
        assert isbn1.is_valid

        # 0-8044-2957-X (valid ISBN-10 with check digit 'X')
        isbn2 = Isbn.parse("0-8044-2957-X")
        assert isbn2 is not None
        assert isbn2.is_valid

    def test_valid_isbn13(self) -> None:
        # 978-5-17-069255-2
        isbn = Isbn.parse("978-5-17-069255-2")
        assert isbn is not None
        assert isbn.is_valid
        assert isbn.clean_digits == "9785170692552"

    def test_invalid_isbn_checksum(self) -> None:
        # Alter last digit
        isbn = Isbn.parse("978-5-17-069255-9")
        assert isbn is not None
        assert not isbn.is_valid

    def test_reject_placeholder_isbns(self) -> None:
        # Obvious fake/placeholder ISBNs
        placeholders = [
            "978-5-0000-0000-0",
            "0000000000",
            "9780000000000",
            "978-9-9999-9999-9",
        ]
        for p in placeholders:
            isbn = Isbn.parse(p)
            assert isbn is not None
            assert not isbn.is_valid

    def test_empty_isbn_returns_none(self) -> None:
        assert Isbn.parse("") is None
        assert Isbn.parse("   ") is None
        assert Isbn.parse(None) is None


class TestEan13ValueObject:
    def test_valid_ean13_generation(self) -> None:
        ean = Ean13.from_article("DP-B-10005")
        assert len(ean.value) == 13
        assert ean.value.isdigit()
        assert ean.value.startswith("297847")
        assert Ean13.validate_checksum(ean.value)

    def test_dirty_article_generates_valid_ean13(self) -> None:
        """Adversarial QA from test_hardcore_audit.py: barcode dirty article."""
        ean = Ean13.from_article("DP-B-ABC-!@#")
        assert len(ean.value) == 13
        assert ean.value.isdigit()
        assert Ean13.validate_checksum(ean.value)

    def test_invalid_ean13_raises(self) -> None:
        with pytest.raises(ValidationError):
            Ean13("12345")  # Too short
        with pytest.raises(ValidationError):
            Ean13("2978470100059")  # Bad checksum


class TestDimensionsValueObject:
    def test_dimensions_float_string_no_crash(self) -> None:
        """Adversarial QA from test_hardcore_audit.py: Dimensions float string."""
        dims = Dimensions.from_dict({
            "width": "130.5",
            "length": "205.0",
            "height": "15",
            "weight": "250.5",
        })
        assert dims.width_mm == 130
        assert dims.length_mm == 205
        assert dims.height_mm == 15
        assert dims.weight_g == 250

    def test_dimensions_defaults_on_empty(self) -> None:
        dims = Dimensions.from_dict({})
        assert dims.width_mm == 130
        assert dims.length_mm == 205
        assert dims.height_mm == 15
        assert dims.weight_g == 250


class TestPriceValueObject:
    def test_price_parsing(self) -> None:
        p1 = Price.parse("1250")
        assert p1.amount == 1250.0
        assert str(p1) == "1250 ₽"

        p2 = Price.parse(" 1 450.50 руб ")
        assert p2.amount == 1450.50
        assert str(p2) == "1450.50 ₽"

    def test_negative_price_raises(self) -> None:
        with pytest.raises(ValidationError):
            Price(-10.0)


class TestDomainEnums:
    def test_photo_role_background_removal_rule(self) -> None:
        assert PhotoRole.COVER_FRONT.should_remove_background
        assert PhotoRole.COVER_BACK.should_remove_background
        assert not PhotoRole.INFO_PAGES.should_remove_background
        assert not PhotoRole.MANTRA_DEFECTS.should_remove_background
        assert not PhotoRole.ILLUSTRATIONS.should_remove_background

    def test_photo_role_ai_vision_candidate(self) -> None:
        assert PhotoRole.COVER_FRONT.is_ai_vision_candidate
        assert PhotoRole.COVER_BACK.is_ai_vision_candidate
        assert PhotoRole.INFO_PAGES.is_ai_vision_candidate
        assert not PhotoRole.MANTRA_DEFECTS.is_ai_vision_candidate
        assert not PhotoRole.ILLUSTRATIONS.is_ai_vision_candidate

    def test_photo_role_from_str_aliases(self) -> None:
        assert PhotoRole.from_str("лицевая") == PhotoRole.COVER_FRONT
        assert PhotoRole.from_str("задник") == PhotoRole.COVER_BACK
        assert PhotoRole.from_str("титул") == PhotoRole.INFO_PAGES
        assert PhotoRole.from_str("дефект") == PhotoRole.MANTRA_DEFECTS
        assert PhotoRole.from_str("иллюстрация") == PhotoRole.ILLUSTRATIONS

    def test_book_condition_from_str(self) -> None:
        assert BookCondition.from_str("новая") == BookCondition.NEW
        assert BookCondition.from_str("как новая") == BookCondition.FINE
        assert BookCondition.from_str("очень хорошая") == BookCondition.VERY_GOOD
        assert BookCondition.from_str("удовлетворительная") == BookCondition.SATISFACTORY
        assert BookCondition.from_str("плохое состояние") == BookCondition.POOR

    def test_book_era_and_sync_enums(self) -> None:
        assert BookEra.PRE2011.value == "pre2011"
        assert BookEra.POST2011.value == "post2011"
        assert AssetStatus.UPLOADED.value == "UPLOADED"
        assert OzonSyncStatus.QUEUED.value == "QUEUED"

    def test_field_source_provenance_priority(self) -> None:
        assert FieldSource.EMPTY < FieldSource.DEFAULT
        assert FieldSource.DEFAULT < FieldSource.AI_GEMINI
        assert FieldSource.AI_GEMINI < FieldSource.DB_CANONICAL
        assert FieldSource.DB_CANONICAL < FieldSource.FANTLAB_EXACT
        assert FieldSource.FANTLAB_EXACT < FieldSource.USER_MANUAL
