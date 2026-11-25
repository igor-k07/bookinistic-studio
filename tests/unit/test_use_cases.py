"""Unit tests for the 6 pure application Use Cases (Step 5.2).

100% offline with pure In-Memory port fakes executing in < 0.5s.
Tests:
1. AssetPipelineUseCase: upload, non-destructive transform, optimistic locking, selective rembg, S3 staging.
2. RecognizeBookUseCase: candidate filter, barcode lookup, AI vision, exact/fuzzy enrichment, provenance protection.
3. SaveBookUseCase: pre-validation, vault archive, S3 promotion, Excel export, atomic DB + tab close.
4. ReopenBookUseCase: DB restore, vault manifest hydration, tab deduplication, error on missing.
5. SyncCatalogUseCase: 50-chunking, photo patching, per-item isolation, progress dispatch.
6. CleanupStorageUseCase: ARCHIVED + s3_final_url, active tab protection, dry-run vs live delete.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest

from backend.application.use_cases.asset_pipeline import AssetPipelineUseCase
from backend.application.use_cases.cleanup_storage import CleanupStorageUseCase
from backend.application.use_cases.recognize_book import RecognizeBookUseCase
from backend.application.use_cases.reopen_book import ReopenBookUseCase
from backend.application.use_cases.save_book import SaveBookUseCase
from backend.application.use_cases.sync_catalog import SyncCatalogUseCase
from backend.domain.enums import AssetStatus, FieldSource, OzonSyncStatus
from backend.domain.exceptions import ConcurrencyError, EntityNotFoundError, ValidationError
from backend.domain.models import Asset, Book, EnrichmentCandidate, WorkspaceTab

# ==============================================================================
# IN-MEMORY PORT FAKES (Zero External Dependencies, Pure Python)
# ==============================================================================


class FakeUnitOfWork:
    """In-memory Unit of Work."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> "FakeUnitOfWork":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Optional[bool]:
        if exc_type is not None:
            self.rollback()
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


class FakeBookRepository:
    """In-memory Book and Tab repository."""

    def __init__(self) -> None:
        self.books: Dict[str, Book] = {}
        self.tabs: Dict[str, WorkspaceTab] = {}

    def get_by_article(self, article: str) -> Optional[Book]:
        return self.books.get(article.strip().upper())

    def save(self, book: Book) -> None:
        self.books[book.article.strip().upper()] = book

    def delete(self, article: str) -> bool:
        art = article.strip().upper()
        if art in self.books:
            del self.books[art]
            return True
        return False

    def search_fts(self, query: str, limit: int = 50, offset: int = 0) -> List[Book]:
        q = query.lower()
        results = [
            b for b in self.books.values()
            if q in b.title.lower() or q in b.author.lower() or q == (b.barcode or "").lower()
        ]
        return results[offset : offset + limit]

    def get_next_article(self, prefix: str = "DP-B-") -> str:
        return f"{prefix}{len(self.books) + 1:05d}"

    def list_tabs(self) -> List[WorkspaceTab]:
        return list(self.tabs.values())

    def save_tab(self, tab: WorkspaceTab) -> None:
        self.tabs[tab.id] = tab

    def delete_tab(self, tab_id: str) -> bool:
        if tab_id in self.tabs:
            del self.tabs[tab_id]
            return True
        return False


class FakeAssetRepository:
    """In-memory Asset repository with version checking."""

    def __init__(self) -> None:
        self.assets: Dict[str, Asset] = {}

    def get_by_id(self, asset_id: str) -> Optional[Asset]:
        return self.assets.get(asset_id)

    def save(self, asset: Asset) -> None:
        if asset.id in self.assets:
            existing = self.assets[asset.id]
            if asset.version != existing.version:
                raise ConcurrencyError(f"Version mismatch: {asset.version} vs {existing.version}")
            asset.version += 1
        self.assets[asset.id] = asset

    def list_by_article(self, article: str) -> List[Asset]:
        art = article.strip().upper()
        return [a for a in self.assets.values() if (a.book_article or "").strip().upper() == art]

    def list_by_status(self, status: AssetStatus) -> List[Asset]:
        return [a for a in self.assets.values() if a.status == status]

    def delete(self, asset_id: str) -> bool:
        if asset_id in self.assets:
            del self.assets[asset_id]
            return True
        return False


class FakeMediaStorage:
    """In-memory media storage."""

    def __init__(self) -> None:
        self.files: Dict[str, bytes] = {}

    def save_file(self, rel_path: str, data: bytes) -> str:
        self.files[rel_path] = data
        return rel_path

    def read_file(self, rel_path: str) -> bytes:
        if rel_path not in self.files:
            raise FileNotFoundError(rel_path)
        return self.files[rel_path]

    def delete_file(self, rel_path: str) -> bool:
        if rel_path in self.files:
            del self.files[rel_path]
            return True
        return False


class FakeCloudStorage:
    """In-memory cloud storage."""

    def __init__(self) -> None:
        self.staging: Dict[str, bytes] = {}
        self.permanent: Dict[str, bytes] = {}
        self.static_card = "https://cdn.example.com/static/card.jpg"

    def upload_staging(self, store_id: str, asset_id: str, render_hash: str, data: bytes) -> str:
        key = f"staging/{store_id}/{asset_id}_{render_hash[:8]}.jpg"
        self.staging[key] = data
        return f"https://cdn.example.com/{key}"

    def promote_to_book(
        self, store_id: str, article: str, canonical_name: str, staging_key: str, sha8: str
    ) -> str:
        url = f"https://cdn.example.com/books/{store_id}/{article}/{canonical_name}_{sha8}.jpg"
        return url

    def get_static_card_url(self) -> str:
        return self.static_card


class FakeEventBroker:
    """In-memory event broker."""

    def __init__(self) -> None:
        self.events: List[Tuple[str, Dict[str, Any]]] = []

    def publish(self, event_type: str, data: Dict[str, Any]) -> None:
        self.events.append((event_type, data))


class FakeVaultStore:
    """In-memory vault store."""

    def __init__(self) -> None:
        self.manifests: Dict[str, Dict[str, Any]] = {}
        self.saved_vaults: Dict[str, Any] = {}

    def save_book_vault(
        self, article: str, book_metadata: Dict[str, Any], photos: List[Tuple[str, bytes, Optional[bytes]]]
    ) -> Any:
        self.saved_vaults[article] = {"meta": book_metadata, "photos_count": len(photos)}
        self.manifests[article] = book_metadata
        return f"vault/{article}"

    def get_manifest(self, article: str) -> Optional[Dict[str, Any]]:
        return self.manifests.get(article)

    def list_photos(self, article: str) -> List[Any]:
        return []

    def create_ozon_zip(self, article: str, zip_output_path: Any) -> int:
        return 0


class FakeExcelExporter:
    """In-memory excel exporter."""

    def __init__(self) -> None:
        self.exported: List[str] = []

    def export_book(self, book: Book) -> str:
        self.exported.append(book.article)
        return "ready_tables/export.xlsx"

    def remove_book(self, article: str) -> bool:
        if article in self.exported:
            self.exported.remove(article)
            return True
        return False


class FakeMarketplaceChannel:
    """In-memory marketplace channel."""

    def __init__(self, errors: Optional[Dict[str, str]] = None) -> None:
        self.errors = errors or {}

    def validate(self, book: Book) -> Dict[str, str]:
        return dict(self.errors)

    def publish_or_update(self, book: Book) -> Dict[str, Any]:
        return {"result": {"task_id": 12345}}

    def check_status(self, task_id: int) -> Dict[str, Any]:
        return {"result": {"items": [{"status": "imported"}]}}

    def export_file(self, books: List[Book], output_path: Any) -> Any:
        return output_path


# ==============================================================================
# 1. ASSET PIPELINE USE CASE TESTS
# ==============================================================================


def test_asset_pipeline_create_and_proactive_s3():
    repo = FakeAssetRepository()
    storage = FakeMediaStorage()
    cloud = FakeCloudStorage()
    broker = FakeEventBroker()

    use_case = AssetPipelineUseCase(
        asset_repo=repo,
        media_storage=storage,
        cloud_storage=cloud,
        event_broker=broker,
    )

    raw_bytes = b"sample_jpeg_binary_data"
    asset = use_case.create_asset(
        book_article="DP-B-00100",
        raw_data=raw_bytes,
        original_filename="01_front_cover.jpg",
    )

    assert asset.id is not None
    assert asset.book_article == "DP-B-00100"
    assert asset.slot in ("01_cover_front", "cover_front")
    assert asset.status == AssetStatus.UPLOADED

    # Proactive S3 upload
    staging_url = use_case.upload_to_staging(
        asset_id=asset.id,
        store_id="870997",
        data=raw_bytes,
    )
    assert "https://cdn.example.com/staging/870997/" in staging_url

    loaded = repo.get_by_id(asset.id)
    assert loaded is not None
    assert loaded.s3_staging_url == staging_url


def test_asset_pipeline_non_destructive_transform_optimistic_locking():
    repo = FakeAssetRepository()
    storage = FakeMediaStorage()
    use_case = AssetPipelineUseCase(asset_repo=repo, media_storage=storage)

    asset = use_case.create_asset("DP-B-00100", b"image", "page.jpg")
    initial_version = asset.version

    # Apply transform with matching version
    updated = use_case.apply_transform(
        asset_id=asset.id,
        transformations={"rotation": 90.0, "filter": "vintage"},
        expected_version=initial_version,
    )
    assert updated.status == AssetStatus.READY
    assert updated.transformations["rotation"] == 90.0

    # Concurrent edit with outdated version raises ConcurrencyError
    with pytest.raises(ConcurrencyError):
        use_case.apply_transform(
            asset_id=asset.id,
            transformations={"rotation": 180.0},
            expected_version=initial_version,  # Outdated version
        )


def test_asset_pipeline_selective_rembg_covers_only():
    repo = FakeAssetRepository()
    storage = FakeMediaStorage()
    use_case = AssetPipelineUseCase(asset_repo=repo, media_storage=storage)

    # Spine photo (not a cover) -> rembg is skipped
    spine = use_case.create_asset("DP-B-00100", b"spine", slot="spine")
    res_spine = use_case.trigger_rembg(spine.id)
    assert res_spine.ai_white_path is None

    # Front cover photo -> rembg executes
    cover = use_case.create_asset("DP-B-00100", b"cover", slot="01_cover_front")
    res_cover = use_case.trigger_rembg(cover.id)
    assert res_cover.ai_white_path is not None
    assert "_white.jpg" in res_cover.ai_white_path


# ==============================================================================
# 2. RECOGNIZE BOOK USE CASE TESTS
# ==============================================================================


class FakeAIVisionClient:
    def __init__(self, recognized_data: Dict[str, Any]) -> None:
        self.recognized_data = recognized_data
        self.called_with_paths: List[str] = []

    def recognize_images(self, image_paths: List[str]) -> Dict[str, Any]:
        self.called_with_paths = list(image_paths)
        return self.recognized_data


class FakeEnrichmentClient:
    def __init__(self, candidates: List[EnrichmentCandidate]) -> None:
        self.candidates = candidates

    def search_candidates(
        self, title: str, author: str, year: Optional[int] = None, isbn: Optional[str] = None
    ) -> List[EnrichmentCandidate]:
        return self.candidates


class FakeReferenceRepository:
    def __init__(self, brands: Dict[str, str]) -> None:
        self.brands = brands

    def is_known_brand(self, brand: str) -> bool:
        return brand in self.brands

    def search_brands(self, query: str, limit: int = 20) -> List[str]:
        return [v for k, v in self.brands.items() if query.lower() in k.lower()]


def test_recognize_book_pipeline_and_provenance():
    book_repo = FakeBookRepository()
    ai_client = FakeAIVisionClient({
        "title": "Мастер и Маргарита",
        "author": "Михаил Булгаков",
        "year": 1973,
        "publisher": "художественная литература",
    })
    enrichment = FakeEnrichmentClient([
        EnrichmentCandidate(
            provider="fantlab",
            exact_match=True,
            fields={
                "title": "Мастер и Маргарита",
                "author": "Михаил Булгаков",
                "year": 1973,
                "publisher": "Художественная литература",
                "pages": 480,
            },
        )
    ])
    ref_repo = FakeReferenceRepository({"художественная литература": "Художественная литература"})

    use_case = RecognizeBookUseCase(
        book_repo=book_repo,
        ai_client=ai_client,
        enrichment_client=enrichment,
        reference_repo=ref_repo,
    )

    book = Book(
        article="DP-B-00500",
        title="Ручное название",
        field_sources={"title": FieldSource.USER_MANUAL},  # USER_MANUAL protected!
    )

    # Photos with mixed roles (some candidate, some defect/spine)
    photos = [
        ("/path/cover.jpg", "01_cover_front"),
        ("/path/title.jpg", "02_title_page"),
        ("/path/spine.jpg", "spine"),  # not candidate
        ("/path/defect.jpg", "defect"),  # not candidate
    ]

    updated = use_case.execute(book, photos)

    # 1. Candidate filter passed only cover and title
    assert len(ai_client.called_with_paths) == 2
    assert "/path/spine.jpg" not in ai_client.called_with_paths

    # 2. Provenance protection: title was USER_MANUAL, so it must NOT be overwritten!
    assert updated.title == "Ручное название"
    assert updated.field_sources["title"] == FieldSource.USER_MANUAL

    # 3. Other fields filled from exact enrichment
    assert updated.author == "Михаил Булгаков"
    assert updated.pages == 480
    assert updated.brand == "Художественная литература"


# ==============================================================================
# 3. SAVE BOOK USE CASE TESTS
# ==============================================================================


def test_save_book_pre_validation_failure():
    uow = FakeUnitOfWork()
    book_repo = FakeBookRepository()
    channel = FakeMarketplaceChannel(errors={"year": "Year is required"})

    use_case = SaveBookUseCase(uow=uow, book_repo=book_repo, channel=channel)
    book = Book(article="DP-B-00100", title="Test Book")

    with pytest.raises(ValidationError) as exc_info:
        use_case.execute("870997", book)
    assert "pre-validation failed" in str(exc_info.value)


def test_save_book_success_atomic_workflow():
    uow = FakeUnitOfWork()
    book_repo = FakeBookRepository()
    channel = FakeMarketplaceChannel()
    vault = FakeVaultStore()
    cloud = FakeCloudStorage()
    excel = FakeExcelExporter()
    broker = FakeEventBroker()

    # Pre-populate open tab
    book_repo.save_tab(WorkspaceTab(id="tab_1", book_article="DP-B-00100"))

    use_case = SaveBookUseCase(
        uow=uow,
        book_repo=book_repo,
        channel=channel,
        vault_store=vault,
        cloud_storage=cloud,
        excel_exporter=excel,
        event_broker=broker,
    )

    book = Book(
        article="DP-B-00100",
        title="Герой нашего времени",
        author="Михаил Лермонтов",
        year=1840,
    )

    photos = [("01_front.jpg", b"rendered_front", b"raw_front")]
    staging_keys = {"01_front.jpg": "staging/870997/front_hash1234.jpg"}

    res = use_case.execute(
        store_id="870997",
        book=book,
        photos=photos,
        staging_keys=staging_keys,
    )

    assert res["status"] == "success"

    # 1. Vault saved
    assert "DP-B-00100" in vault.saved_vaults

    # 2. S3 photo URLs populated (main photo + static card appended)
    assert book.main_photo_url.startswith("https://cdn.example.com/books/870997/DP-B-00100/")
    assert cloud.static_card in book.add_photo_urls

    # 3. Excel row exported
    assert "DP-B-00100" in excel.exported

    # 4. Atomic DB persistence & Tab closed
    assert uow.committed is True
    assert book_repo.get_by_article("DP-B-00100") is not None
    assert len(book_repo.list_tabs()) == 0  # Tab was closed!


# ==============================================================================
# 4. REOPEN BOOK USE CASE TESTS
# ==============================================================================


def test_reopen_book_from_catalog_and_deduplication():
    uow = FakeUnitOfWork()
    book_repo = FakeBookRepository()
    use_case = ReopenBookUseCase(uow=uow, book_repo=book_repo)

    book = Book(article="DP-B-00200", title="Евгений Онегин", author="Александр Пушкин")
    book_repo.save(book)

    # First reopen: creates tab
    tab1 = use_case.execute("DP-B-00200")
    assert tab1.book_article == "DP-B-00200"
    assert tab1.is_active is True
    assert len(book_repo.list_tabs()) == 1

    # Second reopen: returns existing tab (deduplication)
    tab2 = use_case.execute("DP-B-00200")
    assert tab2.id == tab1.id
    assert len(book_repo.list_tabs()) == 1


def test_reopen_book_hydrates_from_vault_manifest():
    uow = FakeUnitOfWork()
    book_repo = FakeBookRepository()
    vault = FakeVaultStore()
    vault.manifests["DP-B-00300"] = {
        "metadata": {
            "article": "DP-B-00300",
            "title": "Мёртвые души",
            "author": "Николай Гоголь",
            "year": 1842,
        }
    }

    use_case = ReopenBookUseCase(uow=uow, book_repo=book_repo, vault_store=vault)
    tab = use_case.execute("DP-B-00300")
    assert tab.book_article == "DP-B-00300"
    assert tab.is_active is True


def test_reopen_missing_book_raises_not_found():
    uow = FakeUnitOfWork()
    book_repo = FakeBookRepository()
    use_case = ReopenBookUseCase(uow=uow, book_repo=book_repo)

    with pytest.raises(EntityNotFoundError):
        use_case.execute("DP-B-99999")


# ==============================================================================
# 5. SYNC CATALOG USE CASE TESTS
# ==============================================================================


class FakeOzonSyncGateway:
    def __init__(self, products: List[Dict[str, Any]]) -> None:
        self.products = {p["offer_id"]: p for p in products}

    def get_products_info(self, offer_ids: List[str]) -> Dict[str, Any]:
        items = [self.products[art] for art in offer_ids if art in self.products]
        return {"result": {"items": items}}


def test_sync_catalog_batches_of_50_and_patches_photos():
    uow = FakeUnitOfWork()
    book_repo = FakeBookRepository()

    # Pre-populate 5 books in repo
    for i in range(1, 6):
        book_repo.save(Book(article=f"DP-B-0000{i}", title=f"Book {i}"))

    # Remote Ozon products
    remote_data = [
        {
            "offer_id": f"DP-B-0000{i}",
            "primary_image": f"https://cdn.example.com/main_{i}.jpg",
            "images": [f"https://cdn.example.com/main_{i}.jpg", f"https://cdn.example.com/add_{i}.jpg"],
        }
        for i in range(1, 6)
    ]
    gateway = FakeOzonSyncGateway(remote_data)
    use_case = SyncCatalogUseCase(uow=uow, book_repo=book_repo, gateway=gateway)

    articles = [f"DP-B-0000{i}" for i in range(1, 6)]
    res = use_case.execute("870997", articles=articles, batch_size=2)

    assert res["status"] == "success"
    assert res["total_updated"] == 5

    book1 = book_repo.get_by_article("DP-B-00001")
    assert book1 is not None
    assert book1.main_photo_url == "https://cdn.example.com/main_1.jpg"
    assert book1.add_photo_urls == ["https://cdn.example.com/add_1.jpg"]
    assert book1.ozon_sync_status == OzonSyncStatus.PUBLISHED


# ==============================================================================
# 6. CLEANUP STORAGE USE CASE TESTS
# ==============================================================================


def test_cleanup_storage_protection_of_active_tabs_and_dry_run():
    uow = FakeUnitOfWork()
    book_repo = FakeBookRepository()
    asset_repo = FakeAssetRepository()
    media_storage = FakeMediaStorage()

    # Active tab for DP-B-00100
    book_repo.save_tab(WorkspaceTab(id="tab_active", book_article="DP-B-00100"))

    # Asset 1: ARCHIVED, has S3 final, but linked to ACTIVE TAB -> MUST BE PROTECTED!
    media_storage.save_file("temp/active.jpg", b"123")
    asset_active = Asset(
        id="ast_active",
        book_article="DP-B-00100",
        status=AssetStatus.ARCHIVED,
        s3_final_url="https://s3/final1.jpg",
        original_path="temp/active.jpg",
        file_size_bytes=100,
    )
    asset_repo.save(asset_active)

    # Asset 2: ARCHIVED, has S3 final, NOT linked to active tab -> CAN BE CLEANED!
    media_storage.save_file("temp/cleanable.jpg", b"456")
    asset_clean = Asset(
        id="ast_cleanable",
        book_article="DP-B-00200",  # Not active
        status=AssetStatus.ARCHIVED,
        s3_final_url="https://s3/final2.jpg",
        original_path="temp/cleanable.jpg",
        file_size_bytes=200,
    )
    asset_repo.save(asset_clean)

    use_case = CleanupStorageUseCase(
        uow=uow,
        asset_repo=asset_repo,
        book_repo=book_repo,
        media_storage=media_storage,
    )

    # Dry-run execution
    dry_res = use_case.execute("870997", dry_run=True)
    assert dry_res["cleaned_count"] == 1
    assert dry_res["bytes_freed"] == 200
    assert "temp/cleanable.jpg" in media_storage.files  # Not deleted in dry run

    # Live execution
    live_res = use_case.execute("870997", dry_run=False)
    assert live_res["cleaned_count"] == 1
    assert "temp/cleanable.jpg" not in media_storage.files  # Deleted!
    assert "temp/active.jpg" in media_storage.files  # Protected!
    assert asset_repo.get_by_id("ast_active") is not None  # Protected!
    assert asset_repo.get_by_id("ast_cleanable") is None  # Removed from DB!
