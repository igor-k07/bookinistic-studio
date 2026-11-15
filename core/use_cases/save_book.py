"""
save_book.py: Сценарий (Use Case) сохранения книги.
Инкапсулирует оркестрацию: канонизация по базам -> локальный vault -> выгрузка S3 -> SQLite -> Excel -> авто-очистка.
"""

import os
from typing import Any, Dict, List, Optional

from config import PORT, SESSION_PHOTOS_DIR, INBOX_DIR
from core.domain.enums import TemplateMode
from core.domain.models import Book
from services.db_service import get_next_article_number, reconcile_with_references, save_book_to_db
from services.excel_service import append_book_to_excel
from services.s3_service import upload_book_photos as s3_upload_book_photos
import services.tunnel_service as tunnel_service
from services.vault_service import save_book_vault_photos


class SaveBookUseCase:
    """
    Оркестратор полного цикла сохранения книги букинистического магазина.
    Изолирует бизнес-логику от транспортного уровня HTTP.
    """

    def execute(self, book_input: Dict[str, Any]) -> Dict[str, Any]:
        """
        Выполняет сценарий сохранения книги.
        Принимает словарь с данными из формы, возвращает результат операции.
        """
        # 1. Приведение к доменной модели
        book = Book.from_dict(book_input)

        # 2. Нечувствительная к регистру сверка и канонизация по базам catalog.db
        book_dict = book.to_dict()
        try:
            reconciled = reconcile_with_references(book_dict)
            book = Book.from_dict(reconciled)
        except Exception as rec_err:
            print(f"⚠️ [SaveBookUseCase] Ошибка канонизации: {rec_err}", flush=True)

        # 3. Гарантия уникального артикула DP-B-XXXXX
        if not book.article:
            book.article = get_next_article_number()

        # 4. Применение чистых доменных правил (сохранность, ГОСТ-габариты, аннотация)
        book.sanitize_domain_rules(allow_overwrite_manual_dims=False)

        # 5. Сохранение обработанных фото в локальный архив books_vault/
        slots_photos = book.slots_photos or {}
        folder_name, saved_files = save_book_vault_photos(
            book.article,
            book.title,
            slots_photos,
        )
        book.vault_folder = folder_name

        # 6. Выгрузка в Yandex Object Storage (S3 CDN) с вечными публичными HTTPS-ссылками Ozon
        s3_main_url, s3_add_urls = None, ""
        try:
            s3_main_url, s3_add_urls = s3_upload_book_photos(book.article, book.title, slots_photos)
        except Exception as s3_err:
            print(f"⚠️ [SaveBookUseCase] S3 недоступен (используем туннель): {s3_err}", flush=True)

        tunnel_url = ""
        if s3_main_url:
            book.main_photo_url = s3_main_url
            book.add_photo_urls = s3_add_urls
        else:
            # Fallback: резервный туннель Cloudflare
            tunnel_url = tunnel_service.get_tunnel_url()
            if not tunnel_url:
                tunnel_url = tunnel_service.start_tunnel(PORT)

            if tunnel_url and book.article and saved_files:
                main_photo = "01_cover_front.jpg" if "01_cover_front.jpg" in saved_files else saved_files[0]
                book.main_photo_url = f"{tunnel_url}/vault/{book.article}/{main_photo}"

                add_files = [
                    f for f in saved_files
                    if f != main_photo
                    and not f.startswith(f"{book.article}")
                    and not f.startswith("info_page")
                ]
                card_file = "99_card.jpg" if "99_card.jpg" in add_files else None
                add_files_no_card = [f for f in add_files if f != "99_card.jpg"]
                if card_file:
                    add_files = add_files_no_card[:13] + [card_file]
                else:
                    add_files = add_files_no_card[:14]

                if add_files:
                    book.add_photo_urls = " ".join([f"{tunnel_url}/vault/{book.article}/{f}" for f in add_files])

        # 7. Сохранение книги в локальную базу данных SQLite (catalog.db)
        save_book_to_db(book.to_dict())

        # 8. Запись книги в официальную таблицу Excel Ozon (pre2011 или post2011)
        excel_result = append_book_to_excel(book.to_dict())

        # 9. Авто-очистка временных файлов сессии с диска Mac (п. 6.2 спецификации)
        self._cleanup_temporary_session_photos(slots_photos)

        # 10. Формирование ответа
        response_data = dict(excel_result)
        response_data["article"] = book.article
        response_data["title"] = book.title
        response_data["saved_photos"] = saved_files
        response_data["vault_folder"] = folder_name
        response_data["tunnel_url"] = tunnel_url or ""
        response_data["main_photo_url"] = book.main_photo_url
        response_data["add_photo_urls"] = book.add_photo_urls
        response_data["s3_enabled"] = bool(s3_main_url)
        return response_data

    def _cleanup_temporary_session_photos(self, slots_photos: Dict[str, Any]) -> None:
        """
        Удаляет временные тяжелые файлы с диска Mac после успешного сохранения в Vault/S3 (п. 6.2 спецификации).
        Удаляет все варианты (cameraOriginal, aiWhiteOriginal, croppedBase, preview).
        """
        if not slots_photos:
            return

        import re

        def _cleanup_photo_variations(p_dict: dict):
            if not isinstance(p_dict, dict):
                return
            p_id = p_dict.get("id") or ""
            prefixes = set()
            if p_id:
                prefixes.add(p_id)
            for k in ("url", "local_path", "preview", "name"):
                val = p_dict.get(k)
                if isinstance(val, str) and "photo_" in val:
                    m = re.search(r"(photo_[a-z0-9]+)", val)
                    if m:
                        prefixes.add(m.group(1))

            if prefixes and os.path.exists(SESSION_PHOTOS_DIR):
                try:
                    for fname in os.listdir(SESSION_PHOTOS_DIR):
                        for pref in prefixes:
                            if fname.startswith(pref):
                                try:
                                    os.remove(os.path.join(SESSION_PHOTOS_DIR, fname))
                                except Exception:
                                    pass
                except Exception:
                    pass

        for slot_val in slots_photos.values():
            if isinstance(slot_val, dict):
                _cleanup_photo_variations(slot_val)
            elif isinstance(slot_val, list):
                for item in slot_val:
                    if isinstance(item, dict):
                        _cleanup_photo_variations(item)

