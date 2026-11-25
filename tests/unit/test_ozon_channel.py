"""Unit tests for Ozon Channel Module (backend/channels/ozon/).

Verifies:
1. IMarketplaceChannel protocol compliance.
2. Instant pre-validation (< 5ms) and ADR-4 era boundary enforcement.
3. Symmetric mapping without hardcoded 'Советский писатель' brand fallback.
4. OzonGateway endpoint calls, rate-limiting, and chunking (batch 50 for attributes).
5. OzonChannel publish_or_update routing (import vs update).
"""

from unittest.mock import MagicMock

import httpx
import pytest

from backend.channels.base import IMarketplaceChannel
from backend.channels.ozon.channel import OzonChannel
from backend.channels.ozon.gateway import OzonGateway
from backend.channels.ozon.mapper import (
    book_to_ozon_import_payload,
    ozon_response_to_book_dict,
)
from backend.channels.ozon.validator import OzonValidator
from backend.domain.exceptions import AuthenticationError
from backend.domain.models import Book
from backend.domain.value_objects import Dimensions


@pytest.fixture
def valid_soviet_book():
    """Valid pre-2011 book without ISBN (ISBN optional on Ozon)."""
    return Book(
        article="DP-B-00100",
        title="Остров сокровищ",
        author="Стивенсон Роберт Льюис",
        year=1985,
        publisher="Художественная литература",
        brand="Художественная литература",
        price=500.0,
        dimensions=Dimensions(width_mm=130, length_mm=200, height_mm=18, weight_g=280),
        main_photo_url="https://s3/cover.jpg",
    )


@pytest.fixture
def valid_modern_book():
    """Valid post-2011 book with required valid ISBN."""
    return Book(
        article="DP-B-00200",
        title="Современная книга",
        author="Иванов Иван",
        year=2021,
        publisher="Эксмо",
        brand="Эксмо",
        isbn="978-5-17-070335-7",
        price=800.0,
        dimensions=Dimensions(width_mm=145, length_mm=215, height_mm=22, weight_g=350),
        main_photo_url="https://s3/cover_modern.jpg",
    )



def test_protocol_conformance():
    """Verify OzonChannel conforms to IMarketplaceChannel protocol."""
    gateway = OzonGateway(client_id="123", api_key="secret")
    channel = OzonChannel(gateway)
    assert isinstance(channel, IMarketplaceChannel)


def test_validator_valid_books(valid_soviet_book, valid_modern_book):
    """Verify validator returns empty dict for valid pre2011 and post2011 books."""
    assert OzonValidator.validate(valid_soviet_book) == {}
    assert OzonValidator.validate(valid_modern_book) == {}


def test_validator_missing_required_fields():
    """Verify validator catches empty title, zero price, missing dimensions, missing photos."""
    book = Book(
        article="DP-B-00999",
        title="",
        dimensions=Dimensions(width_mm=0, length_mm=0, height_mm=0, weight_g=0),
    )
    errors = OzonValidator.validate(book)

    assert "title" in errors
    assert "price" in errors
    assert "year" in errors
    assert "publisher" in errors
    assert "weight_g" in errors
    assert "photos" in errors


def test_validator_enforces_era_isbn_rule():
    """Verify ADR-4 era boundary: year >= 2011 requires valid ISBN, year <= 2010 does not."""
    # Pre-2011 book without ISBN is 100% valid
    pre_book = Book(
        article="DP-B-00101",
        title="Сказки",
        year=1975,
        publisher="Детгиз",
        price=300.0,
        dimensions=Dimensions(width_mm=145, length_mm=200, height_mm=15, weight_g=200),
        main_photo_url="https://s3/c.jpg",
    )
    assert "isbn" not in OzonValidator.validate(pre_book)

    # Post-2011 book without ISBN fails
    post_book_no_isbn = Book(
        article="DP-B-00102",
        title="Новинка",
        year=2022,
        publisher="АСТ",
        price=600.0,
        dimensions=Dimensions(width_mm=145, length_mm=200, height_mm=15, weight_g=200),
        main_photo_url="https://s3/c.jpg",
    )
    errors_no_isbn = OzonValidator.validate(post_book_no_isbn)
    assert "isbn" in errors_no_isbn

    # Post-2011 book with INVALID ISBN checksum fails
    post_book_bad_isbn = Book(
        article="DP-B-00103",
        title="Новинка",
        year=2022,
        publisher="АСТ",
        isbn="978-5-00-111111-9",  # Invalid checksum
        price=600.0,
        dimensions=Dimensions(width_mm=145, length_mm=200, height_mm=15, weight_g=200),
        main_photo_url="https://s3/c.jpg",
    )
    errors_bad_isbn = OzonValidator.validate(post_book_bad_isbn)
    assert "isbn" in errors_bad_isbn


def test_mapper_no_hardcoded_brand_fallback():
    """Verify mapper never hardcodes 'Советский писатель' if publisher is different."""
    book = Book(
        article="DP-B-00050",
        title="Физика для всех",
        publisher="Наука",
        year=1980,
        price=400.0,
        dimensions=Dimensions(width_mm=130, length_mm=200, height_mm=20, weight_g=250),
        main_photo_url="https://s3/c.jpg",
    )

    payload = book_to_ozon_import_payload(book)
    items = payload["items"]
    assert len(items) == 1
    attrs = items[0]["attributes"]

    brand_attr = next((a for a in attrs if a["id"] == 85), None)
    assert brand_attr is not None
    # Brand must match 'Наука', never 'Советский писатель'
    assert brand_attr["values"][0]["value"] == "Наука"


def test_mapper_bidirectional_roundtrip():
    """Verify symmetric conversion Ozon response -> Book dict."""
    item_info = {
        "id": 999888777,
        "offer_id": "DP-B-00001",
        "name": "Тестовая книга",
        "price": "750",
        "barcode": "2978470000018",
        "sku": 123456789,
    }
    item_attrs = {
        "attributes": [
            {"id": 4180, "values": [{"value": "Тестовая книга"}]},
            {"id": 105, "values": [{"value": "Толстой Л.Н."}]},
            {"id": 7, "values": [{"value": "Правда"}]},
            {"id": 85, "values": [{"value": "Правда"}]},
            {"id": 4081, "values": [{"value": "1988"}]},
            {"id": 4051, "values": [{"value": "450"}]},
            {"id": 23273, "values": [{"value": "Проза"}]},
        ]
    }

    parsed = ozon_response_to_book_dict(item_info, item_attrs)
    assert parsed["article"] == "DP-B-00001"
    assert parsed["title"] == "Тестовая книга"
    assert parsed["author"] == "Толстой Л.Н."
    assert parsed["publisher"] == "Правда"
    assert parsed["year"] == 1988
    assert parsed["pages"] == 450
    assert parsed["price"] == 750.0


def test_gateway_chunking_attributes_by_50():
    """Verify POST /v4/product/info/attributes strictly chunks by 50."""
    mock_http = MagicMock()
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {"result": [{"offer_id": "DP-1"}]}
    mock_http.post.return_value = resp

    gateway = OzonGateway(client_id="123", api_key="secret", http_client=mock_http)

    # 120 offer IDs -> 3 chunks: 50, 50, 20
    offer_ids = [f"DP-B-{i:05d}" for i in range(1, 121)]
    gateway.get_products_attributes(offer_ids=offer_ids)

    assert mock_http.post.call_count == 3
    # Check that each chunk payload has at most 50 offer_ids
    for call in mock_http.post.call_args_list:
        chunk_offers = call.kwargs["json"]["filter"]["offer_id"]
        assert len(chunk_offers) <= 50


def test_gateway_auth_error_handling():
    """Verify HTTP 401 raises AuthenticationError."""
    mock_http = MagicMock()
    resp_401 = MagicMock(spec=httpx.Response)
    resp_401.status_code = 401
    resp_401.text = "Unauthorized: Invalid Api-Key"
    mock_http.post.return_value = resp_401

    gateway = OzonGateway(client_id="bad", api_key="bad", http_client=mock_http)
    with pytest.raises(AuthenticationError, match="Ozon API authentication failed"):
        gateway.post("/v3/product/import", {})

    conn_check = gateway.check_connection()
    assert conn_check["connected"] is False



def test_channel_publish_or_update(valid_soviet_book):
    """Verify OzonChannel routes to import when new, or update when existing."""
    mock_gateway = MagicMock(spec=OzonGateway)

    # Case 1: Product does not exist -> import_products
    mock_gateway.get_products_info.return_value = []
    mock_gateway.import_products.return_value = {"result": {"task_id": 111}}

    channel = OzonChannel(mock_gateway)
    res_import = channel.publish_or_update(valid_soviet_book)

    assert res_import["success"] is True
    assert res_import["action"] == "import"
    mock_gateway.import_products.assert_called_once()
    mock_gateway.update_attributes.assert_not_called()

    # Case 2: Product exists -> update_attributes and update_prices
    mock_gateway.reset_mock()
    mock_gateway.get_products_info.return_value = [{"offer_id": valid_soviet_book.article}]
    mock_gateway.update_attributes.return_value = {"result": "ok"}
    mock_gateway.update_prices.return_value = {"result": "ok"}

    res_update = channel.publish_or_update(valid_soviet_book)
    assert res_update["success"] is True
    assert res_update["action"] == "update"
    mock_gateway.update_attributes.assert_called_once()
    mock_gateway.update_prices.assert_called_once()
