"""External bibliographic enrichment clients (FantLab and OpenLibrary).

Architectural Guarantees:
- 30-day enrichment cache for FantLab API queries in SQLite or memory.
- Bounded concurrency: max 5 parallel detail fetches for editions.
- Strict illustrator role distinction: interior illustrators vs cover/technical designers.
- Cyrillic 'х' (U+0445) formatting in format_mm.
- Semicolon author delimiter.
- Whole-word regex boundary '\\bпо\\b' preventing false-positive foreign author matches (e.g. 'Полевой').
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx

from backend.domain.models import EnrichmentCandidate
from backend.domain.ports import IEnrichmentClient
from backend.domain.value_objects import Isbn
from backend.infrastructure.persistence.sqlite_uow import SqliteUnitOfWork

logger = logging.getLogger(__name__)

# List of foreign author keywords with whole-word regex for short names like 'По' (Edgar Allan Poe)
FOREIGN_AUTHOR_REGEXES = [
    re.compile(r"\bпо\b", re.IGNORECASE),
    re.compile(r"линдгрен", re.IGNORECASE),
    re.compile(r"рид", re.IGNORECASE),
    re.compile(r"верн", re.IGNORECASE),
    re.compile(r"твен", re.IGNORECASE),
    re.compile(r"лондон", re.IGNORECASE),
    re.compile(r"дюма", re.IGNORECASE),
    re.compile(r"толки[е|н]", re.IGNORECASE),
    re.compile(r"конан дойл", re.IGNORECASE),
    re.compile(r"кристи", re.IGNORECASE),
    re.compile(r"уэллс", re.IGNORECASE),
    re.compile(r"киплинг", re.IGNORECASE),
    re.compile(r"азимов", re.IGNORECASE),
    re.compile(r"лем\b", re.IGNORECASE),
    re.compile(r"диккенс", re.IGNORECASE),
    re.compile(r"скотт", re.IGNORECASE),
    re.compile(r"у?айльд", re.IGNORECASE),
    re.compile(r"свифт", re.IGNORECASE),
    re.compile(r"дефо", re.IGNORECASE),
    re.compile(r"хаггард", re.IGNORECASE),
    re.compile(r"брэдбери", re.IGNORECASE),
    re.compile(r"хемингуэй", re.IGNORECASE),
    re.compile(r"ремарк", re.IGNORECASE),
    re.compile(r"оруэлл", re.IGNORECASE),
    re.compile(r"гофман", re.IGNORECASE),
]

ILLUSTRATOR_POSITIVE_ROLES = ("иллюстратор", "иллюстрации", "внутренние иллюстрации", "рисунки", "гравюры")
ILLUSTRATOR_NEGATIVE_ROLES = ("обложка", "оформление", "оформление обложки", "художественный редактор", "макет", "серия")


def is_foreign_author(author: str) -> bool:
    """Check if author matches known foreign authors.

    Critically uses whole-word '\\bпо\\b' so 'Полевой' is NOT classified as Edgar Allan Poe.
    """
    if not author or not author.strip():
        return False
    # If author already contains Latin letters, it's definitely foreign
    if any("a" <= c.lower() <= "z" for c in author):
        return True
    return any(rx.search(author) is not None for rx in FOREIGN_AUTHOR_REGEXES)


def clean_query_text(text: str) -> str:
    """Strip quotes and punctuation for external query strings."""
    return re.sub(r"[\"«».,!?;:()\[\]]", " ", text or "").strip()


def format_cyrillic_dimensions(width: int, length: int) -> str:
    """Format dimensions with Russian Cyrillic 'х' (U+0445), e.g. '145х215'."""
    return f"{width}\u0445{length}"


class OpenLibraryClient:
    """Client for OpenLibrary catalog to find Latin original titles for translated works."""

    def __init__(self, http_client: Optional[httpx.Client] = None) -> None:
        self._client = http_client or httpx.Client(timeout=10.0)

    def find_original_title(self, author: str, title: str) -> Optional[str]:
        """Find Latin original title, skipping search if author is not foreign."""
        if not is_foreign_author(author):
            logger.debug("Author '%s' is not identified as foreign; skipping OpenLibrary", author)
            return None

        clean_a = clean_query_text(author)
        clean_t = clean_query_text(title)
        if not clean_t:
            return None

        q = quote(f"{clean_a} {clean_t}".strip())
        url = f"https://openlibrary.org/search.json?q={q}&limit=3"

        try:
            resp = self._client.get(url, headers={"User-Agent": "BookinisticStudio/2.0"})
            resp.raise_for_status()
            data = resp.json()
            for doc in data.get("docs", []):
                t = doc.get("title", "")
                if t and any("a" <= c.lower() <= "z" for c in t):
                    return str(t).strip()
        except Exception as e:
            logger.warning("OpenLibrary lookup failed for %s - %s: %s", author, title, e)
        return None


class FantLabClient:
    """FantLab API client with 30-day cache, bounded concurrency, and strict role parsing."""

    def __init__(
        self,
        uow: Optional[SqliteUnitOfWork] = None,
        http_client: Optional[httpx.Client] = None,
        max_workers: int = 5,
    ) -> None:
        self.uow = uow
        self._client = http_client or httpx.Client(timeout=10.0)
        self.max_workers = max(1, min(5, max_workers))
        self._mem_cache: Dict[str, Tuple[datetime, Dict[str, Any]]] = {}

    def _get_cache(self, query_hash: str) -> Optional[Dict[str, Any]]:
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if self.uow:
            try:
                with self.uow as uow:
                    if uow.conn is not None:
                        cursor = uow.conn.execute(
                            "SELECT payload_json, expires_at FROM enrichment_cache "
                            "WHERE provider = 'fantlab' AND cache_key = ?",
                            (f"fantlab:{query_hash}",),
                        )
                        row = cursor.fetchone()
                        if row:
                            resp_json, exp_ts = row[0], int(row[1])
                            if exp_ts > now_ts:
                                parsed = json.loads(resp_json)
                                if isinstance(parsed, dict):
                                    return parsed
            except Exception as e:
                logger.warning("Database cache read failed: %s", e)

        now_dt = datetime.now(timezone.utc)
        if query_hash in self._mem_cache:
            exp_dt, cached_val = self._mem_cache[query_hash]
            if exp_dt > now_dt:
                return cached_val
        return None


    def _set_cache(self, query_hash: str, data: Dict[str, Any]) -> None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        expires_ts = int(expires_at.timestamp())

        if self.uow:
            try:
                cache_key = f"fantlab:{query_hash}"
                data_str = json.dumps(data, ensure_ascii=False)
                with self.uow as uow:
                    if uow.conn is not None:
                        uow.conn.execute(
                            "INSERT OR REPLACE INTO enrichment_cache "
                            "(cache_key, provider, payload_json, expires_at) "
                            "VALUES (?, 'fantlab', ?, ?)",
                            (cache_key, data_str, expires_ts),
                        )
                        uow.commit()
            except Exception as e:
                logger.warning("Database cache write failed: %s", e)

        self._mem_cache[query_hash] = (expires_at, data)

    def fetch_edition_details(self, edition_id: int) -> Optional[Dict[str, Any]]:
        """Fetch full edition details from FantLab API."""
        url = f"https://api.fantlab.ru/edition/{edition_id}"
        try:
            resp = self._client.get(
                url, headers={"User-Agent": "BookinisticStudio/2.0 (gzip)"}
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, dict):
                return data
            return None
        except Exception as e:
            logger.warning("FantLab edition/%d fetch failed: %s", edition_id, e)
            return None


    def _extract_illustrators(self, details: Dict[str, Any]) -> str:
        """Extract interior illustrators strictly excluding cover/layout designers."""
        illustrators: List[str] = []
        # Check artists list
        artists = details.get("artists", []) or details.get("autors", [])
        for a in artists:
            if not isinstance(a, dict):
                continue
            role = str(a.get("type", "") or a.get("role", "")).lower()
            name = str(a.get("name", "") or a.get("name_ru", "")).strip()
            if not name:
                continue

            # Check if role matches positive interior illustration roles
            is_pos = any(pos in role for pos in ILLUSTRATOR_POSITIVE_ROLES)
            is_neg = any(neg in role for neg in ILLUSTRATOR_NEGATIVE_ROLES)
            if is_pos and not is_neg:
                illustrators.append(name)

        return "; ".join(dict.fromkeys(illustrators))

    def search_editions(
        self, title: str, author: str, year: Optional[int] = None, isbn: Optional[str] = None
    ) -> List[EnrichmentCandidate]:
        """Search FantLab for editions and return candidates with exact/fuzzy classification."""
        clean_t = clean_query_text(title)
        clean_a = clean_query_text(author)
        q = f"{clean_a} {clean_t}".strip()
        if not q:
            return []

        q_hash = hashlib.sha256(f"{q}:{isbn or ''}:{year or ''}".encode("utf-8")).hexdigest()
        cached = self._get_cache(q_hash)
        if cached:
            matches = cached.get("matches", [])
        else:
            url = f"https://api.fantlab.ru/search-editions?q={quote(q)}"
            try:
                resp = self._client.get(
                    url, headers={"User-Agent": "BookinisticStudio/2.0"}
                )
                resp.raise_for_status()
                data = resp.json()
                matches = data.get("matches", [])
                self._set_cache(q_hash, {"matches": matches})
            except Exception as e:
                logger.warning("FantLab search failed for query '%s': %s", q, e)
                return []

        if not matches:
            return []

        # Fetch details for top matches (bounded to max 5 parallel)
        top_matches = matches[:5]
        edition_details: Dict[int, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_map = {
                executor.submit(self.fetch_edition_details, m["edition_id"]): m["edition_id"]
                for m in top_matches
                if "edition_id" in m
            }
            for fut in as_completed(future_map):
                ed_id = future_map[fut]
                res = fut.result()
                if res:
                    edition_details[ed_id] = res

        candidates: List[EnrichmentCandidate] = []
        for m in top_matches:
            ed_id = m.get("edition_id")
            details = edition_details.get(ed_id, {})
            ed_year = m.get("year")
            ed_isbns = details.get("isbns", []) or ([m.get("isbn")] if m.get("isbn") else [])

            # Check exact match criteria
            is_exact = False
            if isbn:
                clean_isbn = Isbn.clean(isbn)
                for cand_isbn in ed_isbns:
                    if Isbn.clean(cand_isbn) == clean_isbn:
                        is_exact = True
                        break
            elif year and ed_year == year:
                is_exact = True

            authors_list = m.get("authors", [])
            if isinstance(authors_list, list):
                author_str = "; ".join(str(a.get("name", "")) for a in authors_list if isinstance(a, dict))
            else:
                author_str = str(m.get("author", ""))

            illustrator_str = self._extract_illustrators(details)
            format_code = details.get("format", "") or m.get("format", "")

            fields: Dict[str, Any] = {
                "title": m.get("name") or m.get("title") or title,
                "author": author_str or author,
                "year": ed_year,
                "publisher": m.get("publisher", ""),
                "isbn": ed_isbns[0] if ed_isbns else "",
                "pages": details.get("pages") or m.get("pages"),
                "book_format_code": format_code,
                "illustrator": illustrator_str,
            }
            candidates.append(
                EnrichmentCandidate(
                    provider="fantlab",
                    exact_match=is_exact,
                    fields=fields,
                )
            )

        return candidates


class UnifiedEnrichmentClient(IEnrichmentClient):
    """Facade combining FantLab editions search and OpenLibrary original title lookup."""

    def __init__(
        self,
        fantlab: Optional[FantLabClient] = None,
        openlibrary: Optional[OpenLibraryClient] = None,
        uow: Optional[SqliteUnitOfWork] = None,
    ) -> None:
        self.fantlab = fantlab or FantLabClient(uow=uow)
        self.openlibrary = openlibrary or OpenLibraryClient()

    def search_candidates(
        self, title: str, author: str, year: Optional[int] = None, isbn: Optional[str] = None
    ) -> List[EnrichmentCandidate]:
        candidates = self.fantlab.search_editions(title, author, year, isbn)

        # Enhance with OpenLibrary original title if foreign author
        orig_title = self.openlibrary.find_original_title(author, title)
        if orig_title:
            for cand in candidates:
                cand.fields["original_title"] = orig_title

        return candidates
