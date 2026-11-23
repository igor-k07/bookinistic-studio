"""
save_book.py: Сценарий (Use Case) сохранения книги.
Инкапсулирует оркестрацию: канонизация по базам -> локальный vault -> выгрузка S3 -> SQLite -> Excel -> авто-очистка.
"""

import os
from typing import Any, Dict, List, Optional

from config import PORT, SESSION_PHOTOS_DIR, INBOX_DIR
from core.domain.enums import TemplateMode
from core.domain.models import Book
from core.domain.rules import (
    SLOT_CARD,
    SLOT_COVER_FRONT,
    SLOT_INFO_PAGES,
    classify_filename_to_slot,
    get_canonical_photo_filename,
)
from services.db_service import (
    check_article_exists,
    get_next_article_number,
    reconcile_with_references,
    save_book_to_db,
)
from services.excel_service import append_book_to_excel, sync_book_to_excel
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

        is_edit = bool(
            book_input.get("is_edit")
            or book_input.get("isReopened")
            or book_input.get("is_saved_to_excel")
            or book_input.get("mode") == "edit"
        )

        # 3. Гарантия уникального артикула DP-B-XXXXX и защита от случайной перезаписи
        if not book.article:
            book.article = get_next_article_number(verify_ozon=True)
        else:
            if not is_edit:
                art_check = check_article_exists(book.article, check_ozon=True)
                if art_check.get("exists"):
                    existing_title = art_check.get("title") or "существующий товар"
                    suggested = get_next_article_number(verify_ozon=True)
                    raise ValueError(
                        f"Артикул {book.article} уже занят («{existing_title}»)! Перезапись заблокирована. "
                        f"Для создания новой книги используйте свободный артикул {suggested}, "
                        f"либо включите режим редактирования карточки."
                    )

        # 4. Применение чистых доменных правил (сохранность, ГОСТ-габариты, аннотация)
        book.sanitize_domain_rules(allow_overwrite_manual_dims=False)

        # 4.1. Авто-кадрирование обложки по безопасному контуру (+3.5%), если оператор не кадрировал вручную
        slots_photos = book.slots_photos or {}
        cf = slots_photos.get("cover_front")
        if cf and isinstance(cf, dict):
            crop_rel = cf.get("aiCropRelative") or cf.get("crop_relative")
            is_cropped = cf.get("isCropped") or bool(cf.get("croppedBase"))
            if crop_rel and not is_cropped and isinstance(crop_rel, dict):
                try:
                    from services.vault_service import resolve_photo_bytes
                    img_bytes = resolve_photo_bytes(cf)
                    if img_bytes:
                        import io
                        import base64
                        from PIL import Image
                        im = Image.open(io.BytesIO(img_bytes))
                        w, h = im.size
                        cx = max(0, int(crop_rel.get("x", 0) * w))
                        cy = max(0, int(crop_rel.get("y", 0) * h))
                        cw = int(crop_rel.get("w", 1.0) * w)
                        ch = int(crop_rel.get("h", 1.0) * h)
                        if cw > 40 and ch > 40:
                            cropped_im = im.crop((cx, cy, min(w, cx + cw), min(h, cy + ch)))
                            buf = io.BytesIO()
                            cropped_im.save(buf, format="JPEG", quality=90, optimize=True)
                            cf["croppedBase"] = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
                            cf["isCropped"] = True
                except Exception as crop_err:
                    print(f"⚠️ [SaveBookUseCase] Ошибка авто-кадрирования обложки: {crop_err}")

        # 5. Сохранение обработанных фото в локальный архив books_vault/
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
                non_card_files = [f for f in saved_files if classify_filename_to_slot(f) != SLOT_CARD]
                canonical_cover = get_canonical_photo_filename("cover_front")
                if canonical_cover in saved_files:
                    main_photo = canonical_cover
                elif non_card_files:
                    main_photo = non_card_files[0]
                else:
                    main_photo = None

                if main_photo:
                    book.main_photo_url = f"{tunnel_url}/vault/{book.article}/{main_photo}"
                else:
                    book.main_photo_url = ""

                add_files = [
                    f for f in saved_files
                    if f != main_photo
                    and not f.startswith(f"{book.article}")
                    and classify_filename_to_slot(f) != SLOT_INFO_PAGES
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

        # 7.1. Помечаем ассеты книги в SQLite статусом ARCHIVED
        if slots_photos:
            try:
                from services.db_service import get_db_connection
                with get_db_connection() as conn:
                    for s_name, s_val in slots_photos.items():
                        p_items = s_val if isinstance(s_val, list) else ([s_val] if s_val else [])
                        for itm in p_items:
                            if isinstance(itm, dict) and itm.get("id"):
                                conn.execute(
                                    "UPDATE assets SET status = 'ARCHIVED', book_article = ? WHERE id = ?",
                                    (book.article, str(itm["id"])),
                                )
                    conn.commit()
            except Exception as ast_err:
                print(f"⚠️ [SaveBookUseCase] Ошибка архивации ассетов в SQLite: {ast_err}")

        # 8. Синхронизация книги с официальной таблицей Excel Ozon (и для новых, и для обновляемых книг)
        excel_result = sync_book_to_excel(book.to_dict())

        # 8.1. Выгрузка / обновление в Ozon Seller API (если подключено)
        ozon_info = None
        if is_edit:
            # Обновление фото на Ozon через Seller API
            if s3_main_url:
                try:
                    import services.ozon_service as ozon_service
                    imgs = [u for u in (book.add_photo_urls or "").split() if u]
                    ozon_service.update_ozon_product_pictures(book.article, s3_main_url, imgs)
                except Exception as e_p:
                    print(f"⚠️ [SaveBookUseCase] Ошибка update_ozon_product_pictures: {e_p}")

            # Обновление атрибутов книги на Ozon
            try:
                import services.ozon_service as ozon_service
                conn_status = ozon_service.check_ozon_connection()
                if conn_status.get("connected"):
                    ok_ozon, ozon_res = ozon_service.publish_product_to_ozon(book.to_dict())
                    t_id = (ozon_res if isinstance(ozon_res, dict) else {}).get("task_id")
                    ozon_info = {"published": ok_ozon, "task_id": t_id, "result": ozon_res}
            except Exception as e_oz:
                ozon_info = {"published": False, "error": str(e_oz)}
        else:
            try:
                import services.ozon_service as ozon_service
                conn_status = ozon_service.check_ozon_connection()
                if conn_status.get("connected"):
                    ok_ozon, ozon_res = ozon_service.publish_product_to_ozon(book.to_dict())
                    if ok_ozon:
                        t_id = (ozon_res if isinstance(ozon_res, dict) else {}).get("task_id")
                        ozon_info = {
                            "published": True,
                            "task_id": t_id,
                            "result": ozon_res,
                        }
                        print(f"🚀 [SaveBookUseCase] Карточка {book.article} успешно создана на Ozon (task_id: {t_id})")
                    else:
                        ozon_info = {"published": False, "error": str(ozon_res)}
                        print(f"⚠️ [SaveBookUseCase] Ошибка создания карточки на Ozon: {ozon_res}")
            except Exception as ozon_err:
                ozon_info = {"published": False, "error": str(ozon_err)}
                print(f"⚠️ [SaveBookUseCase] Сбой обращения к Ozon API: {ozon_err}")

        # 9. Авто-очистка временных файлов сессии с диска Mac (п. 6.2 спецификации)
        self._cleanup_temporary_session_photos(slots_photos)

        # 10. Формирование ответа
        response_data = dict(excel_result)
        response_data["is_edit"] = is_edit
        response_data["article"] = book.article
        response_data["title"] = book.title
        response_data["saved_photos"] = saved_files
        response_data["vault_folder"] = folder_name
        response_data["tunnel_url"] = tunnel_url or ""
        response_data["main_photo_url"] = book.main_photo_url
        response_data["add_photo_urls"] = book.add_photo_urls
        response_data["s3_enabled"] = bool(s3_main_url)
        response_data["ozon_info"] = ozon_info
        if is_edit:
            response_data["message"] = f"Карточка {book.article} успешно обновлена в таблице Excel и в базе!"

        # Получаем постоянные объекты слотов из vault (вечные ссылки /vault/ и S3 взамен очищенных временных файлов)
        try:
            from services.vault_service import reopen_book_from_vault
            reopened = reopen_book_from_vault(book.article)
            if reopened and "slots" in reopened:
                response_data["slots"] = reopened["slots"]
        except Exception as reopen_err:
            print(f"⚠️ [SaveBookUseCase] Не удалось получить слоты из vault: {reopen_err}")

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

