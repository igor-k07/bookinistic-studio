"""Unit tests for domain rules, normalization, and GOST physics (Step 1.4)."""


from backend.domain.enums import BookCondition, BookEra
from backend.domain.rules import (
    calculate_book_condition,
    calculate_physical_dimensions,
    classify_filename_to_slot,
    clean_publisher_name,
    format_annotation_with_warning,
    get_canonical_photo_filename,
    normalize_author_name,
    resolve_book_era,
)


class TestBookEraResolution:
    def test_clean_years(self) -> None:
        assert resolve_book_era(1980) == BookEra.PRE2011
        assert resolve_book_era(2010) == BookEra.PRE2011
        assert resolve_book_era(2011) == BookEra.POST2011
        assert resolve_book_era(2024) == BookEra.POST2011

    def test_dirty_year_strings(self) -> None:
        assert resolve_book_era("1985 г.") == BookEra.PRE2011
        assert resolve_book_era("2010 г.") == BookEra.PRE2011
        assert resolve_book_era("2012-2013") == BookEra.POST2011
        assert resolve_book_era("[2011]") == BookEra.POST2011
        assert resolve_book_era("б.г.") == BookEra.PRE2011
        assert resolve_book_era(None) == BookEra.PRE2011
        assert resolve_book_era("") == BookEra.PRE2011


class TestBookConditionAndAnnotation:
    def test_calculate_condition(self) -> None:
        assert calculate_book_condition(has_defects=False) == BookCondition.VERY_GOOD
        assert calculate_book_condition(has_defects=True) == BookCondition.GOOD
        assert calculate_book_condition(has_defects=False, manual_condition="Хорошая") == BookCondition.GOOD
        assert calculate_book_condition(has_defects=False, manual_condition="Удовлетворительное") == BookCondition.SATISFACTORY
        assert calculate_book_condition(has_defects=False, manual_condition="Плохое") == BookCondition.POOR

    def test_annotation_warning_idempotency(self) -> None:
        once = format_annotation_with_warning("Описание книги.", has_defects=True)
        twice = format_annotation_with_warning(once, has_defects=True)
        assert once == twice
        assert twice.count("ВНИМАНИЕ! КНИГА НЕ НОВАЯ") == 1

    def test_annotation_empty_remains_empty(self) -> None:
        assert format_annotation_with_warning("", has_defects=True) == ""
        assert format_annotation_with_warning("   ", has_defects=False) == ""


class TestPhysicalDimensions:
    def test_float_string_no_crash(self) -> None:
        gost = calculate_physical_dimensions(
            format_code="84x108/32",
            pages=200,
            existing_dimensions={"width": "130.5"},
            allow_overwrite_manual=True,
        )
        assert gost["width_mm"] == 130
        assert gost["length_mm"] == 200

    def test_dust_jacket_bug_fixed(self) -> None:
        """Dust-jacket ('суперобложка') must be treated as hardcover (spine add = 6, not soft 4)."""
        hard = calculate_physical_dimensions(
            format_code="84x108/32",
            pages=300,
            cover_type="Твердый переплет",
        )
        dust_jacket = calculate_physical_dimensions(
            format_code="84x108/32",
            pages=300,
            cover_type="Суперобложка",
        )
        soft = calculate_physical_dimensions(
            format_code="84x108/32",
            pages=300,
            cover_type="Мягкая обложка",
        )
        # Spine of hardcover and dust-jacket should be equal and thicker than softcover
        assert hard["height_mm"] == dust_jacket["height_mm"]
        assert dust_jacket["height_mm"] > soft["height_mm"]

    def test_manual_dimensions_protected(self) -> None:
        existing = {"width": 150, "length": 220, "height": 30, "weight": 500}
        gost = calculate_physical_dimensions(
            format_code="84x108/32",
            pages=100,
            existing_dimensions=existing,
            allow_overwrite_manual=False,
        )
        assert gost["width_mm"] == 150
        assert gost["length_mm"] == 220
        assert gost["height_mm"] == 30
        assert gost["weight_g"] == 500


class TestPublisherAndAuthorCleaning:
    def test_publisher_cleaning_word_boundary_bug(self) -> None:
        """'Идея-Пресс' must NOT be mangled to 'ея-Пресс' by greedy 'ид' prefix."""
        assert clean_publisher_name("Идея-Пресс") == "Идея-Пресс"
        assert clean_publisher_name("Издательство «Наука»") == "Наука"
        assert clean_publisher_name("Изд-во Эксмо") == "Эксмо"
        assert clean_publisher_name("Издательский дом 'Питер'") == "Питер"
        assert clean_publisher_name("ИД Мещерякова") == "Мещерякова"

    def test_author_normalization(self) -> None:
        assert normalize_author_name("") == "не указан"
        assert normalize_author_name("Автор не указан") == "не указан"
        assert normalize_author_name("неизвестен") == "не указан"
        assert normalize_author_name("Лев Толстой") == "Лев Толстой"


class TestSlotClassification:
    def test_token_boundaries_no_false_positive(self) -> None:
        # 'cardigan' or 'background' must not match 'card' or 'back'
        assert classify_filename_to_slot("background.jpg") != "cover_back"
        assert classify_filename_to_slot("cardigan.jpg") != "card"

        # Legitimate slots
        assert classify_filename_to_slot("01_cover_front.jpg") == "cover_front"
        assert classify_filename_to_slot("04_cover_back.jpg") == "cover_back"
        assert classify_filename_to_slot("99_card.jpg") == "card"
        assert classify_filename_to_slot("info_page_1.jpg") == "info_pages"
        assert classify_filename_to_slot("02_defect_1.jpg") == "mantra_defects"

    def test_canonical_filename_generation(self) -> None:
        assert get_canonical_photo_filename("cover_front") == "01_cover_front.jpg"
        assert get_canonical_photo_filename("cover_back") == "04_cover_back.jpg"
        assert get_canonical_photo_filename("cover_back", index=2, is_multi=True) == "04_cover_back_2.jpg"
        assert get_canonical_photo_filename("mantra_defects", index=1) == "02_defect_1.jpg"
        assert get_canonical_photo_filename("illustrations", index=3) == "03_illustration_3.jpg"
        assert get_canonical_photo_filename("card") == "99_card.jpg"
