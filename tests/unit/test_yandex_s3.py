"""Unit tests for Two-Tier Yandex S3 Adapter (backend/infrastructure/cloud/yandex_s3.py).

Verifies:
1. ICloudStorage Protocol compliance.
2. Content-hash deduplication (avoids put_object when object already exists).
3. Server-side copy_object during promote_to_book.
4. Static warning card handling (static/99_card.jpg).
5. Ozon 14-photo cap with 99_card.jpg strictly placed last.
6. Batch parallel staging and promotion.
7. Key sanitization and ASCII URL formatting.
"""

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError

from backend.domain.exceptions import StorageError
from backend.domain.ports import ICloudStorage
from backend.infrastructure.cloud.yandex_s3 import YandexS3Adapter, sanitize_s3_key


@pytest.fixture
def mock_s3_client():
    """Mocked boto3 S3 client."""
    client = MagicMock()
    return client


@pytest.fixture
def s3_adapter(mock_s3_client):
    """Adapter with mocked boto3 client."""
    return YandexS3Adapter(
        bucket="test-bucket",
        endpoint_url="https://storage.yandexcloud.net",
        s3_client=mock_s3_client,
        max_workers=4,
    )


def test_protocol_conformance(s3_adapter):
    """Verify YandexS3Adapter satisfies ICloudStorage protocol."""
    assert isinstance(s3_adapter, ICloudStorage)
    assert s3_adapter.is_configured is True


def test_sanitize_s3_key():
    """Verify safe ASCII sanitization."""
    assert sanitize_s3_key("staging/870997/test.jpg") == "staging/870997/test.jpg"
    assert sanitize_s3_key("staging//870997///test.jpg") == "staging/870997/test.jpg"
    # Cyrillic or special chars get converted to safe underscores
    assert sanitize_s3_key("staging/книга 1/тест.jpg") == "staging/______1/____.jpg"


def test_upload_staging_new_object(s3_adapter, mock_s3_client):
    """Verify upload_staging uploads when object does not exist."""
    # head_object raises 404
    mock_s3_client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
    )

    data = b"rendered_jpeg_bytes"
    render_hash = "abcdef1234567890"

    url = s3_adapter.upload_staging(
        store_id="870997",
        asset_id="ast_101",
        render_hash=render_hash,
        data=data,
    )

    expected_key = "staging/870997/ast_101_abcdef12.jpg"
    assert url == f"https://storage.yandexcloud.net/test-bucket/{expected_key}"

    # Verify head_object was called to check existence
    mock_s3_client.head_object.assert_called_once_with(
        Bucket="test-bucket", Key=expected_key
    )

    # Verify put_object was called with data
    mock_s3_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key=expected_key,
        Body=data,
        ContentType="image/jpeg",
        CacheControl="public, max-age=86400",
    )


def test_upload_staging_deduplication(s3_adapter, mock_s3_client):
    """Verify upload_staging skips put_object if render_hash object exists."""
    # head_object succeeds (object exists)
    mock_s3_client.head_object.return_value = {"ContentLength": 100}

    data = b"rendered_jpeg_bytes"
    render_hash = "abcdef1234567890"

    url = s3_adapter.upload_staging(
        store_id="870997",
        asset_id="ast_101",
        render_hash=render_hash,
        data=data,
    )

    expected_key = "staging/870997/ast_101_abcdef12.jpg"
    assert url == f"https://storage.yandexcloud.net/test-bucket/{expected_key}"

    # Verify head_object checked existence
    mock_s3_client.head_object.assert_called_once_with(
        Bucket="test-bucket", Key=expected_key
    )

    # Verify put_object was NOT called (dedup hit)
    mock_s3_client.put_object.assert_not_called()


def test_upload_staging_empty_data_rejected(s3_adapter):
    """Verify empty data raises StorageError."""
    with pytest.raises(StorageError, match="Cannot upload empty data"):
        s3_adapter.upload_staging("870997", "ast_1", "hash", b"")


def test_promote_to_book_server_side_copy(s3_adapter, mock_s3_client):
    """Verify promote_to_book uses server-side S3 copy_object."""
    staging_key = "staging/870997/ast_101_abcdef12.jpg"

    url = s3_adapter.promote_to_book(
        store_id="870997",
        article="DP-B-01557",
        canonical_name="01_cover_front.jpg",
        staging_key=staging_key,
        sha8="abcdef12",
    )

    expected_dest = "books/870997/DP-B-01557/01_cover_front_abcdef12.jpg"
    assert url == f"https://storage.yandexcloud.net/test-bucket/{expected_dest}"

    mock_s3_client.copy_object.assert_called_once_with(
        Bucket="test-bucket",
        CopySource={"Bucket": "test-bucket", "Key": staging_key},
        Key=expected_dest,
        CacheControl="public, max-age=31536000, immutable",
    )


def test_promote_to_book_from_full_url(s3_adapter, mock_s3_client):
    """Verify promote_to_book extracts key correctly if full URL passed."""
    staging_url = "https://storage.yandexcloud.net/test-bucket/staging/870997/ast_99_12345678.jpg"

    url = s3_adapter.promote_to_book(
        store_id="870997",
        article="DP-B-01557",
        canonical_name="02_mantra_defects_1",
        staging_key=staging_url,
        sha8="12345678",
    )

    expected_dest = "books/870997/DP-B-01557/02_mantra_defects_1_12345678.jpg"
    assert url == f"https://storage.yandexcloud.net/test-bucket/{expected_dest}"

    mock_s3_client.copy_object.assert_called_once_with(
        Bucket="test-bucket",
        CopySource={"Bucket": "test-bucket", "Key": "staging/870997/ast_99_12345678.jpg"},
        Key=expected_dest,
        CacheControl="public, max-age=31536000, immutable",
    )


def test_ensure_static_card_upload(s3_adapter, mock_s3_client):
    """Verify ensure_static_card uploads single shared static/99_card.jpg."""
    mock_s3_client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404"}}, "HeadObject"
    )

    card_data = b"static_card_image_bytes"
    url = s3_adapter.ensure_static_card(card_data=card_data)

    assert url == "https://storage.yandexcloud.net/test-bucket/static/99_card.jpg"
    mock_s3_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key="static/99_card.jpg",
        Body=card_data,
        ContentType="image/jpeg",
        CacheControl="public, max-age=31536000, immutable",
    )


def test_format_ozon_photo_urls_14_cap(s3_adapter):
    """Verify Ozon 14-photo cap with 99_card.jpg strictly last."""
    main_url = "https://storage.yandexcloud.net/test-bucket/books/870997/DP-B-01/cover.jpg"
    card_url = "https://storage.yandexcloud.net/test-bucket/static/99_card.jpg"

    # Case 1: Under limit (5 photos)
    photos_5 = [f"https://s3/photo_{i}.jpg" for i in range(1, 6)]
    main, add_str = s3_adapter.format_ozon_photo_urls(main_url, photos_5)
    assert main == main_url
    adds = add_str.split()
    assert len(adds) == 6
    assert adds[-1] == card_url

    # Case 2: Exact limit (13 photos + card = 14)
    photos_13 = [f"https://s3/photo_{i}.jpg" for i in range(1, 14)]
    _, add_str_13 = s3_adapter.format_ozon_photo_urls(main_url, photos_13)
    adds_13 = add_str_13.split()
    assert len(adds_13) == 14
    assert adds_13[-1] == card_url

    # Case 3: Over limit (20 photos) -> Strictly 13 photos + card = 14
    photos_20 = [f"https://s3/photo_{i}.jpg" for i in range(1, 21)]
    _, add_str_20 = s3_adapter.format_ozon_photo_urls(main_url, photos_20)
    adds_20 = add_str_20.split()
    assert len(adds_20) == 14
    assert adds_20[-1] == card_url
    assert adds_20[0] == "https://s3/photo_1.jpg"
    assert adds_20[12] == "https://s3/photo_13.jpg"

    # Case 4: No static card
    _, add_str_no_card = s3_adapter.format_ozon_photo_urls(
        main_url, photos_20, include_static_card=False
    )
    adds_no_card = add_str_no_card.split()
    assert len(adds_no_card) == 14
    assert card_url not in adds_no_card


def test_batch_operations(s3_adapter, mock_s3_client):
    """Verify batch upload and promote with ThreadPoolExecutor."""
    mock_s3_client.head_object.side_effect = ClientError(
        {"Error": {"Code": "404"}}, "HeadObject"
    )

    upload_items = [
        ("870997", f"ast_{i}", f"hash_{i}123456", b"data")
        for i in range(5)
    ]
    urls = s3_adapter.batch_upload_staging(upload_items)
    assert len(urls) == 5
    assert all("staging/870997/ast_" in u for u in urls)

    promote_items = [
        ("870997", "DP-B-01557", f"0{i}_photo.jpg", f"staging/870997/ast_{i}.jpg", "12345678")
        for i in range(1, 6)
    ]
    promoted_urls = s3_adapter.batch_promote_to_book(promote_items)
    assert len(promoted_urls) == 5
    assert all("books/870997/DP-B-01557/" in u for u in promoted_urls)
    assert mock_s3_client.copy_object.call_count == 5
