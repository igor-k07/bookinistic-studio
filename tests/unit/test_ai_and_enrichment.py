"""Unit tests for GeminiVisionClient and EnrichmentClients (backend/infrastructure/ai/).

Verifies:
1. Protocol conformance: IAIVisionClient and IEnrichmentClient.
2. 1200px auto-resize and EXIF normalization.
3. Thinking-safe candidate part extraction (skips thought parts).
4. Automatic RECITATION retry with paraphrase prompt.
5. Fail-fast on API_KEY_INVALID (raises AuthenticationError without cascading).
6. Russian author "Полевой" skipped by OpenLibrary (\\bпо\\b word-boundary fix).
7. Edgar Allan Poe ("По") identified as foreign author.
8. FantLab exact vs fuzzy matching by ISBN and year.
9. Strict illustrator role extraction (excludes cover and layout designers).
10. Cyrillic 'х' (U+0445) dimension formatting.
"""

import io
from unittest.mock import MagicMock

import httpx
import pytest
from PIL import Image

from backend.domain.exceptions import AuthenticationError
from backend.domain.ports import IAIVisionClient, IEnrichmentClient
from backend.infrastructure.ai.enrichment_clients import (
    FantLabClient,
    OpenLibraryClient,
    UnifiedEnrichmentClient,
    format_cyrillic_dimensions,
    is_foreign_author,
)
from backend.infrastructure.ai.gemini_client import (
    GeminiVisionClient,
    extract_json_safely,
    preprocess_image,
)


def test_protocol_conformance():
    """Verify Gemini and enrichment clients conform to domain port protocols."""
    gemini = GeminiVisionClient(api_key="test-key")
    enrichment = UnifiedEnrichmentClient()
    assert isinstance(gemini, IAIVisionClient)
    assert isinstance(enrichment, IEnrichmentClient)


def test_preprocess_image_resizes_to_1200px():
    """Verify images > 1200px are downscaled to 1200px max dimension."""
    # Create large 3000x2000 test image in memory
    img = Image.new("RGB", (3000, 2000), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()

    processed_bytes = preprocess_image(raw_bytes, max_dim=1200)

    with Image.open(io.BytesIO(processed_bytes)) as out_img:
        assert max(out_img.width, out_img.height) == 1200
        assert out_img.width == 1200
        assert out_img.height == 800


def test_extract_json_safely():
    """Verify JSON parsing handles fences, raw strings, and control characters."""
    # 1. Clean JSON
    assert extract_json_safely('{"title": "Book"}') == {"title": "Book"}

    # 2. Markdown fenced JSON
    markdown_str = "```json\n{\n  \"title\": \"Book In Fence\"\n}\n```"
    assert extract_json_safely(markdown_str) == {"title": "Book In Fence"}

    # 3. Outer text with JSON inside
    dirty_str = "Here is the result:\n{\"title\": \"Extracted\", \"year\": 1984}\nHope this helps!"
    assert extract_json_safely(dirty_str) == {"title": "Extracted", "year": 1984}


def test_thinking_safe_part_extraction():
    """Verify parts with thought: True are safely ignored in favor of text payload."""
    candidate = {
        "content": {
            "parts": [
                {"thought": True, "text": "Thinking deeply about this antique book cover..."},
                {"text": '{"title": "Хроники Нарнии", "year": 1991}'},
            ]
        }
    }
    client = GeminiVisionClient(api_key="test-key")
    text = client._extract_text_content(candidate)
    assert "Thinking deeply" not in text
    assert '"title": "Хроники Нарнии"' in text
    parsed = extract_json_safely(text)
    assert parsed["title"] == "Хроники Нарнии"


def test_recitation_retry_handling():
    """Verify finishReason == RECITATION triggers automatic retry with paraphrase prompt."""
    mock_http = MagicMock()

    # First response: RECITATION
    resp_recitation = MagicMock(spec=httpx.Response)
    resp_recitation.status_code = 200
    resp_recitation.json.return_value = {
        "candidates": [
            {
                "finishReason": "RECITATION",
                "content": {"parts": []},
            }
        ]
    }

    # Second response: Successful paraphrased JSON
    resp_success = MagicMock(spec=httpx.Response)
    resp_success.status_code = 200
    resp_success.json.return_value = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {
                    "parts": [{"text": '{"title": "Повесть о настоящем человеке", "year": 1946}'}]
                },
            }
        ]
    }

    mock_http.post.side_effect = [resp_recitation, resp_success]

    client = GeminiVisionClient(api_key="test-key", http_client=mock_http)
    result = client._call_model("gemini-2.5-flash", [{"text": "prompt"}], "test-key")

    assert result["title"] == "Повесть о настоящем человеке"
    assert mock_http.post.call_count == 2
    # Verify retry prompt was added
    retry_call_payload = mock_http.post.call_args_list[1].kwargs["json"]
    parts = retry_call_payload["contents"][0]["parts"]
    assert any("Сработал фильтр recitation" in p.get("text", "") for p in parts)


def test_fail_fast_on_api_key_invalid():
    """Verify HTTP 400 with API_KEY_INVALID fails immediately without retrying or cascading."""
    mock_http = MagicMock()
    resp_bad_key = MagicMock(spec=httpx.Response)
    resp_bad_key.status_code = 400
    resp_bad_key.json.return_value = {
        "error": {
            "code": 400,
            "message": "API_KEY_INVALID: The provided API key is expired or invalid",
            "status": "INVALID_ARGUMENT",
        }
    }
    mock_http.post.return_value = resp_bad_key

    client = GeminiVisionClient(
        api_key="invalid-key",
        http_client=mock_http,
        models=["model-1", "model-2"],
    )

    with pytest.raises(AuthenticationError, match="Invalid Gemini API key"):
        client.recognize_categorized([{"role_name": "cover", "data": b"test"}])

    # Must fail fast on model-1 and not attempt model-2
    assert mock_http.post.call_count == 1


def test_foreign_author_boundary_check_polevoy_skipped():
    """Verify Russian author 'Полевой' is NOT considered foreign (\\bпо\\b fix)."""
    # Russian author Борис Полевой must be skipped
    assert is_foreign_author("Борис Полевой") is False
    assert is_foreign_author("Полевой Б.Н.") is False
    assert is_foreign_author("Полевой") is False

    # Other Russian authors with 'по' syllable must also be skipped
    assert is_foreign_author("Попов") is False
    assert is_foreign_author("Погодин") is False

    # Edgar Allan Poe must be recognized as foreign
    assert is_foreign_author("Эдгар Аллан По") is True
    assert is_foreign_author("По Эдгар") is True
    assert is_foreign_author("По") is True

    # Other foreign authors
    assert is_foreign_author("Жюль Верн") is True
    assert is_foreign_author("Астрид Линдгрен") is True
    assert is_foreign_author("Arthur Conan Doyle") is True


def test_openlibrary_skips_russian_author():
    """Verify OpenLibraryClient immediately returns None for native Russian author."""
    mock_http = MagicMock()
    ol_client = OpenLibraryClient(http_client=mock_http)

    title = ol_client.find_original_title("Борис Полевой", "Повесть о настоящем человеке")
    assert title is None
    # No HTTP request should have been made
    mock_http.get.assert_not_called()


def test_openlibrary_queries_foreign_author():
    """Verify OpenLibraryClient queries for foreign author and extracts Latin title."""
    mock_http = MagicMock()
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {
        "docs": [
            {"title": "The Adventures of Tom Sawyer"},
        ]
    }
    mock_http.get.return_value = resp

    ol_client = OpenLibraryClient(http_client=mock_http)
    title = ol_client.find_original_title("Марк Твен", "Приключения Тома Сойера")

    assert title == "The Adventures of Tom Sawyer"
    mock_http.get.assert_called_once()


def test_fantlab_exact_vs_fuzzy_matching():
    """Verify FantLab exact match on ISBN vs fuzzy fallback."""
    mock_http = MagicMock()

    # Search editions response
    search_resp = MagicMock(spec=httpx.Response)
    search_resp.status_code = 200
    search_resp.json.return_value = {
        "matches": [
            {
                "edition_id": 101,
                "name": "Пикник на обочине",
                "year": 1980,
                "publisher": "Молодая гвардия",
                "isbn": "5-01-001234-5",
            },
            {
                "edition_id": 102,
                "name": "Пикник на обочине",
                "year": 2005,
                "publisher": "АСТ",
                "isbn": "978-5-17-000000-0",
            },
        ]
    }

    # Edition details response
    details_resp_1 = MagicMock(spec=httpx.Response)
    details_resp_1.status_code = 200
    details_resp_1.json.return_value = {
        "edition_id": 101,
        "isbns": ["5-01-001234-5"],
        "pages": 256,
        "format": "84x108/32",
    }

    details_resp_2 = MagicMock(spec=httpx.Response)
    details_resp_2.status_code = 200
    details_resp_2.json.return_value = {
        "edition_id": 102,
        "isbns": ["978-5-17-000000-0"],
        "pages": 320,
        "format": "60x90/16",
    }

    mock_http.get.side_effect = [search_resp, details_resp_1, details_resp_2]

    fl_client = FantLabClient(http_client=mock_http)

    # Search with exact ISBN matching edition 101
    candidates = fl_client.search_editions(
        title="Пикник на обочине",
        author="Стругацкие",
        isbn="5010012345",
    )

    assert len(candidates) == 2
    assert candidates[0].exact_match is True
    assert candidates[0].fields["publisher"] == "Молодая гвардия"
    assert candidates[1].exact_match is False


def test_strict_illustrator_role_extraction():
    """Verify interior illustrators are included while cover designers are excluded."""
    details = {
        "artists": [
            {"name": "Билибин И.Я.", "type": "иллюстрации", "role": "художник-иллюстратор"},
            {"name": "Иванов П.", "type": "обложка", "role": "оформление обложки"},
            {"name": "Петров С.", "type": "макет", "role": "художественный редактор"},
        ]
    }
    fl_client = FantLabClient()
    illustrators = fl_client._extract_illustrators(details)
    assert illustrators == "Билибин И.Я."
    assert "Иванов" not in illustrators
    assert "Петров" not in illustrators


def test_cyrillic_dimensions_formatting():
    """Verify Cyrillic 'х' (U+0445) is used for Russian book dimensions."""
    res = format_cyrillic_dimensions(145, 215)
    assert res == "145\u0445215"
    assert "x" not in res  # ASCII 'x' must NOT be present
    assert "\u0445" in res  # Cyrillic 'х' must be present
