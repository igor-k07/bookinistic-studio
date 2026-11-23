"""
core/use_cases/cleanup_temp_files.py: Очистка временных и потерянных фотографий (Garbage Collection).
Безопасно удаляет устаревшие временные файлы из storage/session_photos и storage/inbox,
гарантируя сохранность файлов, упомянутых в активном черновике session_draft.json.
"""

import os
import time
import json
import logging
from typing import Dict, Any, Set

logger = logging.getLogger(__name__)


class CleanupTempFilesUseCase:
    """Use Case для периодической и ручной очистки временного хранилища."""

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        self.base_dir = base_dir
        self.session_photos_dir = os.path.join(base_dir, "storage", "session_photos")
        self.inbox_dir = os.path.join(base_dir, "storage", "inbox")
        self.draft_file = os.path.join(base_dir, "storage", "session_draft.json")

    def get_active_draft_filenames(self) -> Set[str]:
        """Собирает имена всех файлов, на которые ссылается текущий черновик."""
        active_names: Set[str] = set()
        if not os.path.exists(self.draft_file):
            return active_names

        try:
            with open(self.draft_file, "r", encoding="utf-8") as f:
                content = f.read()
                # Быстрый поиск любых упоминаний имен файлов в JSON черновика
                import re
                found = re.findall(r'[\w\-]+(?:_preview|_cameraOriginal|_croppedBase|_aiWhiteOriginal)?\.(?:jpg|jpeg|png)', content, re.IGNORECASE)
                for item in found:
                    active_names.add(os.path.basename(item))
        except Exception as e:
            logger.warning(f"Ошибка чтения session_draft.json при сборке мусора: {e}")

        return active_names

    def execute(self, max_age_hours: float = 24.0, dry_run: bool = False) -> Dict[str, Any]:
        """
        Удаляет файлы старше max_age_hours из временных директорий,
        за исключением файлов активного черновика и служебных (.gitkeep).
        """
        active_files = self.get_active_draft_filenames()
        now = time.time()
        max_age_seconds = max_age_hours * 3600.0

        deleted_count = 0
        deleted_bytes = 0
        kept_count = 0
        errors = []

        dirs_to_clean = [
            ("session_photos", self.session_photos_dir),
            ("inbox", self.inbox_dir)
        ]

        # 1. Очистка временных папок сессии
        for dir_name, dir_path in dirs_to_clean:
            if not os.path.exists(dir_path):
                continue

            for fname in os.listdir(dir_path):
                if fname == ".gitkeep" or fname.startswith("."):
                    continue

                fpath = os.path.join(dir_path, fname)
                if not os.path.isfile(fpath):
                    continue

                if fname in active_files:
                    kept_count += 1
                    continue

                try:
                    st = os.stat(fpath)
                    age = now - st.st_mtime
                    if age > max_age_seconds:
                        fsize = st.st_size
                        if not dry_run:
                            os.remove(fpath)
                        deleted_count += 1
                        deleted_bytes += fsize
                    else:
                        kept_count += 1
                except Exception as e:
                    errors.append(f"{fname}: {str(e)}")

        # 2. Очистка старых локальных папок книг в books_vault (старше 7 дней, если выгружены в S3)
        vault_dir = os.path.join(self.base_dir, "storage", "books_vault")
        vault_ttl_seconds = 7 * 86400.0  # 7 дней
        if os.path.exists(vault_dir):
            import shutil
            try:
                from services.db_service import get_book_from_db
            except Exception:
                get_book_from_db = lambda a: None

            for book_folder in os.listdir(vault_dir):
                b_dir = os.path.join(vault_dir, book_folder)
                if not os.path.isdir(b_dir):
                    continue
                try:
                    st = os.stat(b_dir)
                    if now - st.st_mtime > vault_ttl_seconds:
                        art = book_folder.split("_")[0]
                        db_b = get_book_from_db(art) if callable(get_book_from_db) else None
                        # Удаляем локальный кэш только если книга подтверждена в базе и в S3
                        if db_b and db_b.get("main_photo_url") and "storage.yandexcloud.net" in str(db_b.get("main_photo_url")):
                            dir_size = sum(os.path.getsize(os.path.join(root, f)) for root, _, files in os.walk(b_dir) for f in files)
                            if not dry_run:
                                shutil.rmtree(b_dir)
                            deleted_count += 1
                            deleted_bytes += dir_size
                except Exception as e:
                    errors.append(f"vault {book_folder}: {str(e)}")

        freed_mb = round(deleted_bytes / (1024.0 * 1024.0), 2)
        logger.info(f"Garbage collection ({'dry-run' if dry_run else 'applied'}): "
                    f"удалено {deleted_count} файлов ({freed_mb} MB), сохранено {kept_count}")

        return {
            "success": True,
            "deleted_count": deleted_count,
            "deleted_bytes": deleted_bytes,
            "freed_mb": freed_mb,
            "kept_count": kept_count,
            "dry_run": dry_run,
            "errors": errors
        }

