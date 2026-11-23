"""
vault_service.py: Управление хранилищем фотографий книг books_vault и архивами для Ozon.
"""

import base64
from datetime import datetime
import io
import json
import os
import re
import shutil
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import urllib.request
import zipfile

from config import BASE_DIR, DRAFT_FILE, INBOX_DIR, SESSION_PHOTOS_DIR, VAULT_DIR, get_card_image_path
from core.domain.rules import (
    SLOT_CARD,
    SLOT_COVER_BACK,
    SLOT_COVER_FRONT,
    SLOT_DEFECTS,
    SLOT_ILLUSTRATIONS,
    SLOT_INFO_PAGES,
    classify_filename_to_slot,
    get_canonical_photo_filename,
)


def resolve_photo_bytes(photo_obj_or_data: Any) -> Optional[bytes]:
    """
    Универсально извлекает байты изображения из объекта photo.
    Приоритет строго отдается полностью обработанным данным (data / preview),
    в которых уже запечены свет, контрастность, отбеливание и кадрирование!
    """
    if not photo_obj_or_data:
        return None

    val = photo_obj_or_data
    photo_dict = None
    if isinstance(photo_obj_or_data, dict):
        photo_dict = photo_obj_or_data
        pid = str(photo_dict.get("id") or "")

        # 1. Приоритет #1: готовые отфильтрованные данные (data / preview),
        # сформированные редактором Studio с полным набором пиксельных фильтров
        val = (
            photo_dict.get("data")
            or photo_dict.get("preview")
            or ""
        )

        # 2. Если в объекте нет data/preview, но есть asset_id в реестре ассетов:
        if not val and pid.startswith("ast_"):
            try:
                import services.asset_service as asset_service
                asset = asset_service.get_asset(pid)
                if asset:
                    import tempfile
                    tmp_out = os.path.join(tempfile.gettempdir(), f"render_{pid}_{int(time.time()*1000)}.jpg")
                    if asset_service.render_final_image(pid, tmp_out):
                        try:
                            with open(tmp_out, "rb") as f_tmp:
                                rendered_bytes = f_tmp.read()
                            if os.path.exists(tmp_out):
                                os.remove(tmp_out)
                            if rendered_bytes:
                                return rendered_bytes
                        except Exception:
                            pass
                    cpath = asset.current_path or asset.original_path
                    if cpath and os.path.exists(cpath):
                        with open(cpath, "rb") as f_ast:
                            return f_ast.read()
            except Exception as e:
                print(f"Ошибка извлечения ассета: {e}")

        # 3. Если preview/data не были найдены, проверяем резервные поля
        if not val:
            val = (
                photo_dict.get("croppedBase")
                or photo_dict.get("cameraOriginal")
                or photo_dict.get("rawOriginal")
                or photo_dict.get("url")
                or ""
            )

    if not isinstance(val, str) or not val.strip():
        return None

    val = val.strip()
    raw_bytes = None

    # Base64
    if val.startswith("data:image") or ("," in val and len(val) > 100):
        raw_b64 = val.split(",", 1)[1] if "," in val else val
        try:
            raw_bytes = base64.b64decode(raw_b64)
        except Exception:
            raw_bytes = None
    else:
        # Локальный путь / URL (отсекаем query params ?t=... и hash #...)
        clean_val = val.split("?")[0].split("#")[0]

        def _safe_fetch_url(u_str: str) -> Optional[bytes]:
            try:
                p_parts = urllib.parse.urlsplit(u_str)
                ascii_path = urllib.parse.quote(urllib.parse.unquote(p_parts.path), safe="/:@&=+$,-_.!~*'()")
                ascii_query = urllib.parse.quote(urllib.parse.unquote(p_parts.query), safe="/:@&=+$,-_.!~*'()")
                safe_url = urllib.parse.urlunsplit((p_parts.scheme, p_parts.netloc, ascii_path, ascii_query, p_parts.fragment))
                req = urllib.request.Request(safe_url, headers={"User-Agent": "BookinisticVault/1.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return resp.read()
            except Exception:
                return None

        # Если это URL через наш локальный /api/image_proxy
        if "/api/image_proxy" in val and "url=" in val:
            try:
                parsed_q = urllib.parse.parse_qs(urllib.parse.urlparse(val).query)
                real_target = (parsed_q.get("url") or [""])[0]
                if real_target and (real_target.startswith("http://") or real_target.startswith("https://")):
                    raw_bytes = _safe_fetch_url(real_target)
            except Exception as e_prx:
                pass

        if not raw_bytes and (clean_val.startswith("/") or clean_val.startswith("storage/")):
            clean_rel = clean_val.lstrip("/")
            clean_unquoted = urllib.parse.unquote(clean_rel)
            candidates = [
                os.path.join(BASE_DIR, clean_unquoted),
                os.path.join(BASE_DIR, "storage", clean_unquoted),
                os.path.join(SESSION_PHOTOS_DIR, os.path.basename(clean_unquoted)),
                os.path.join(INBOX_DIR, os.path.basename(clean_unquoted)),
                os.path.join(VAULT_DIR, clean_unquoted.replace("vault/", "", 1) if clean_unquoted.startswith("vault/") else clean_unquoted),
                os.path.join(BASE_DIR, clean_rel),
                os.path.join(BASE_DIR, "storage", clean_rel),
                os.path.join(VAULT_DIR, clean_rel.replace("vault/", "", 1) if clean_rel.startswith("vault/") else clean_rel),
            ]
            for cand in candidates:
                if os.path.exists(cand) and os.path.isfile(cand):
                    try:
                        with open(cand, "rb") as f_in:
                            raw_bytes = f_in.read()
                            break
                    except Exception:
                        pass

        # Если это HTTP/HTTPS URL
        elif clean_val.startswith("http://") or clean_val.startswith("https://"):
            raw_bytes = _safe_fetch_url(clean_val)

        # Обычная base64 строка без data-префикса
        if not raw_bytes and len(val) > 200:
            try:
                raw_bytes = base64.b64decode(val)
            except Exception:
                pass

        # Если удаленная ссылка (S3) не прочиталась по сети, резервно читаем из локального хранилища (url / cameraOriginal)
        if not raw_bytes and photo_dict:
            local_cands = [photo_dict.get("url"), photo_dict.get("cameraOriginal"), photo_dict.get("rawOriginal")]
            for l_cand in local_cands:
                if isinstance(l_cand, str) and (l_cand.startswith("/") or l_cand.startswith("storage/")):
                    clean_l = l_cand.split("?")[0].split("#")[0].lstrip("/")
                    clean_unq = urllib.parse.unquote(clean_l)
                    cand_paths = [
                        os.path.join(BASE_DIR, clean_unq),
                        os.path.join(BASE_DIR, "storage", clean_unq),
                        os.path.join(VAULT_DIR, clean_unq.replace("vault/", "", 1) if clean_unq.startswith("vault/") else clean_unq),
                        os.path.join(BASE_DIR, clean_l),
                    ]
                    for cp in cand_paths:
                        if os.path.exists(cp) and os.path.isfile(cp):
                            try:
                                with open(cp, "rb") as f_in:
                                    raw_bytes = f_in.read()
                                    if raw_bytes:
                                        break
                            except Exception:
                                pass
                    if raw_bytes:
                        break

    if not raw_bytes:
        return None

    # Защитная проверка: если в объекте были заданы яркость/контрастность,
    # а исходник был взят из нефильтрованного источника (cameraOriginal или croppedBase),
    # применяем PIL фильтры, чтобы гарантировать передачу отредактированного света
    if photo_dict and (photo_dict.get("brightness") or photo_dict.get("contrast") or photo_dict.get("whiten")):
        used_raw = False
        if val == photo_dict.get("croppedBase") or val == photo_dict.get("cameraOriginal") or val == photo_dict.get("rawOriginal"):
            used_raw = True

        if used_raw:
            try:
                from PIL import Image, ImageEnhance
                import io
                im = Image.open(io.BytesIO(raw_bytes))
                if im.mode not in ("RGB", "L"):
                    im = im.convert("RGB")

                b_val = float(photo_dict.get("brightness") or 0)
                if b_val != 0:
                    im = ImageEnhance.Brightness(im).enhance(max(0.2, 1.0 + (b_val / 100.0)))

                c_val = float(photo_dict.get("contrast") or 0)
                if c_val != 0:
                    im = ImageEnhance.Contrast(im).enhance(max(0.2, 1.0 + (c_val / 100.0)))

                w_val = float(photo_dict.get("whiten") or 0)
                if w_val > 0:
                    im = ImageEnhance.Brightness(im).enhance(1.0 + (w_val / 200.0))

                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=92, optimize=True)
                raw_bytes = buf.getvalue()
            except Exception as e_pil:
                print(f"⚠️ Ошибка применения фильтров PIL: {e_pil}")

    return raw_bytes


def save_book_vault_photos(
    article: str,
    title: str,
    slots_photos: Optional[Dict[str, Any]]
) -> Tuple[str, List[str]]:
    """Сохраняет обработанные фото книги в архив storage/books_vault/{article}_{clean_title}/"""
    clean_title = re.sub(r"[^\w\s-]", "", title or "book").strip().replace(" ", "_")[:40]
    folder_name = f"{article}_{clean_title}".strip("_")
    book_dir = os.path.join(VAULT_DIR, folder_name)
    os.makedirs(book_dir, exist_ok=True)

    if not slots_photos and not get_card_image_path():
        return folder_name, []

    saved_files = []

    def write_photo(filename, photo_obj, ozon_alt_name=None, is_ozon_photo=True):
        if not photo_obj:
            return
        img_bytes = resolve_photo_bytes(photo_obj)
        if not img_bytes:
            return
        try:
            file_path = os.path.join(book_dir, filename)
            with open(file_path, "wb") as f:
                f.write(img_bytes)
            if is_ozon_photo:
                saved_files.append(filename)
                if ozon_alt_name:
                    alt_path = os.path.join(book_dir, ozon_alt_name)
                    with open(alt_path, "wb") as f:
                        f.write(img_bytes)
        except Exception as e:
            print(f"Ошибка сохранения фото {filename}: {e}")

    if slots_photos:
        raw_sources_dir = os.path.join(book_dir, "raw_sources")
        os.makedirs(raw_sources_dir, exist_ok=True)

        def _archive_raw_source(slot_tag: str, photo_obj: Any, idx: int = 1):
            if not isinstance(photo_obj, dict):
                return
            pid = photo_obj.get("id") or ""
            raw_data = None
            if pid and pid.startswith("ast_"):
                import services.asset_service as asset_service
                asset = asset_service.get_asset(pid)
                if asset and asset.original_path and os.path.exists(asset.original_path):
                    try:
                        shutil.copyfile(asset.original_path, os.path.join(raw_sources_dir, f"{slot_tag}_{idx}_raw.jpg"))
                    except Exception:
                        pass
                    return
            raw_val = photo_obj.get("cameraOriginal") or photo_obj.get("rawOriginal")
            if raw_val:
                raw_bytes = resolve_photo_bytes(raw_val)
                if raw_bytes:
                    try:
                        with open(os.path.join(raw_sources_dir, f"{slot_tag}_{idx}_raw.jpg"), "wb") as f_raw:
                            f_raw.write(raw_bytes)
                    except Exception:
                        pass

        # 1. Обложка (главное фото для Ozon)
        if slots_photos.get("cover_front"):
            write_photo(get_canonical_photo_filename("cover_front"), slots_photos["cover_front"], f"{article}.jpg", is_ozon_photo=True)
            _archive_raw_source("cover_front", slots_photos["cover_front"], 1)

        cur_ozon_idx = 1

        # 2. Фото дефектов при наличии (первые доп. фото для Ozon)
        for idx, p in enumerate(slots_photos.get("mantra_defects", []), 1):
            write_photo(get_canonical_photo_filename("mantra_defects", idx), p, f"{article}_{cur_ozon_idx}.jpg", is_ozon_photo=True)
            _archive_raw_source("defect", p, idx)
            cur_ozon_idx += 1

        # 3. Фото иллюстраций (если есть, идут перед задником)
        for idx, p in enumerate(slots_photos.get("illustrations", []), 1):
            write_photo(get_canonical_photo_filename("illustrations", idx), p, f"{article}_{cur_ozon_idx}.jpg", is_ozon_photo=True)
            _archive_raw_source("illustration", p, idx)
            cur_ozon_idx += 1

        # 4. Фото задников книги (в конце перед карточкой; для комплектов — задники всех книг)
        cb_raw = slots_photos.get("cover_back")
        cb_list = cb_raw if isinstance(cb_raw, list) else ([cb_raw] if cb_raw else [])
        for idx, p in enumerate(cb_list, 1):
            fname = get_canonical_photo_filename("cover_back", idx, is_multi=len(cb_list) > 1)
            write_photo(fname, p, f"{article}_{cur_ozon_idx}.jpg", is_ozon_photo=True)
            _archive_raw_source("cover_back", p, idx)
            cur_ozon_idx += 1

        # Инфо-страницы (титул, оборот) — сохраняем ТОЛЬКО локально для архива и ИИ, НЕ передаем в Ozon!
        for idx, p in enumerate(slots_photos.get("info_pages", []), 1):
            write_photo(get_canonical_photo_filename("info_pages", idx), p, ozon_alt_name=None, is_ozon_photo=False)
            _archive_raw_source("info_page", p, idx)

        # Сохраняем слепок book_state.json для возможности мгновенного Re-open
        try:
            state_file = os.path.join(book_dir, "book_state.json")
            state_data = {
                "article": article,
                "title": title,
                "saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "slots_photos": slots_photos,
            }
            with open(state_file, "w", encoding="utf-8") as f_st:
                json.dump(state_data, f_st, ensure_ascii=False, indent=2)
        except Exception as st_err:
            print(f"⚠️ Ошибка записи book_state.json: {st_err}")

    # 5. Финальное шаблонное фото с предупреждением (card.png) — всегда в самом конце
    card_path = get_card_image_path()
    if card_path and os.path.exists(card_path):
        try:
            # Сохраняем и как .png, и как .jpg (т.к. исходный файл card - это JPEG)
            for ext in (".jpg", ".png"):
                shutil.copyfile(card_path, os.path.join(book_dir, f"99_card{ext}"))
                shutil.copyfile(card_path, os.path.join(book_dir, f"{article}_card{ext}"))
            saved_files.append("99_card.jpg")
        except Exception as e:
            print(f"Ошибка копирования card в {book_dir}: {e}")

    return folder_name, saved_files


def create_photos_zip(article_req: str = "") -> Tuple[bytes, str]:
    """
    Формирует ZIP-архив с фото для Ozon (для одной книги или всех книг).
    Исключает служебные титульные страницы (info_page).
    Возвращает (zip_bytes, zip_filename).
    """
    zip_buffer = io.BytesIO()
    today_date = datetime.now().strftime("%d.%m.%Y")
    zip_filename = f"{today_date}_all_ozon_photos.zip"

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        if article_req:
            zip_filename = f"{article_req}_ozon_photos.zip"
            matched_folder = None
            if os.path.exists(VAULT_DIR):
                for d in os.listdir(VAULT_DIR):
                    if d == article_req or d.startswith(f"{article_req}_"):
                        matched_folder = os.path.join(VAULT_DIR, d)
                        break
            if matched_folder and os.path.isdir(matched_folder):
                for fname in sorted(os.listdir(matched_folder)):
                    if (
                        fname.lower().endswith((".jpg", ".jpeg", ".png"))
                        and not fname.startswith(("03_info_page", "info_page"))
                    ):
                        fpath = os.path.join(matched_folder, fname)
                        zf.write(fpath, arcname=fname)
        else:
            if os.path.exists(VAULT_DIR):
                for root, _, files in os.walk(VAULT_DIR):
                    for fname in sorted(files):
                        if (
                            fname.lower().endswith((".jpg", ".jpeg", ".png"))
                            and not fname.startswith(("03_info_page", "info_page"))
                        ):
                            fpath = os.path.join(root, fname)
                            rel = os.path.relpath(fpath, VAULT_DIR)
                            zf.write(fpath, arcname=rel)

    return zip_buffer.getvalue(), zip_filename


def _persist_b64_to_disk(photo_id: str, suffix: str, val: Any) -> Optional[str]:
    """Сохраняет base64 изображение на диск в SESSION_PHOTOS_DIR и возвращает путь URL."""
    if not val or not isinstance(val, str):
        return None
    val = val.strip()
    if not val:
        return None
    if val.startswith("/") or val.startswith("storage/"):
        return val

    raw_b64 = val.split(",", 1)[1] if "," in val else val
    try:
        data_bytes = base64.b64decode(raw_b64)
        if len(data_bytes) < 10:
            return None
    except Exception:
        return None

    clean_id = re.sub(r"[^\w-]", "_", photo_id)
    filename = f"{clean_id}_{suffix}.jpg"
    os.makedirs(SESSION_PHOTOS_DIR, exist_ok=True)
    full_path = os.path.join(SESSION_PHOTOS_DIR, filename)
    with open(full_path, "wb") as f_out:
        f_out.write(data_bytes)
    ts = int(time.time() * 1000)
    return f"/session_photos/{filename}?t={ts}"



def save_session_draft_file(draft_data: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    """
    Оптимизирует черновик сессии:
    1. Извлекает base64 изображения из photoPool и сохраняет на диск в storage/session_photos/
    2. Очищает избыточные копии полей (data, history)
    3. Приводит слоты книг в booksSession к компактным ссылкам по ID
    4. Записывает компактный JSON черновика в DRAFT_FILE (< 100 KB)
    5. Возвращает карту обновленных URL для синхронизации в памяти клиента
    """
    os.makedirs(SESSION_PHOTOS_DIR, exist_ok=True)
    updated_urls: Dict[str, Dict[str, str]] = {}

    photo_pool = draft_data.get("photoPool")
    if not isinstance(photo_pool, list):
        photo_pool = []
        draft_data["photoPool"] = photo_pool

    books_session = draft_data.get("booksSession")
    if not isinstance(books_session, list):
        books_session = []
        draft_data["booksSession"] = books_session

    # Гарантируем, что любые фото, прикрепленные к слотам, есть в photoPool
    existing_ids = {p["id"] for p in photo_pool if isinstance(p, dict) and "id" in p}
    for book in books_session:
        if not isinstance(book, dict):
            continue
        slots = book.get("slots")
        if not isinstance(slots, dict):
            continue
        item = slots.get("cover_front")
        if isinstance(item, dict) and "id" in item and item["id"] not in existing_ids:
            photo_pool.append(item)
            existing_ids.add(item["id"])
        for s in ("cover_back", "info_pages", "illustrations", "mantra_defects"):
            items = slots.get(s)
            if isinstance(items, list):
                for it in items:
                    if isinstance(it, dict) and "id" in it and it["id"] not in existing_ids:
                        photo_pool.append(it)
                        existing_ids.add(it["id"])
            elif isinstance(items, dict) and "id" in items and items["id"] not in existing_ids:
                photo_pool.append(items)
                existing_ids.add(items["id"])

    # 1. Сохраняем фото на диск и обновляем ссылки
    for photo in photo_pool:
        if not isinstance(photo, dict):
            continue
        pid = str(photo.get("id") or f"photo_{int(time.time() * 1000)}")
        clean_id = re.sub(r"[^\w-]", "_", pid)

        # Камера / исходник
        raw_orig_val = photo.get("cameraOriginal") or photo.get("rawOriginal") or photo.get("preview")
        cam_url = _persist_b64_to_disk(clean_id, "cameraOriginal", raw_orig_val)
        if cam_url:
            photo["cameraOriginal"] = cam_url
            photo["rawOriginal"] = cam_url

        # Обрезанная база
        if photo.get("croppedBase"):
            crop_url = _persist_b64_to_disk(clean_id, "croppedBase", photo["croppedBase"])
            if crop_url:
                photo["croppedBase"] = crop_url

        # ИИ-фон
        if photo.get("aiWhiteOriginal"):
            ai_url = _persist_b64_to_disk(clean_id, "aiWhiteOriginal", photo["aiWhiteOriginal"])
            if ai_url:
                photo["aiWhiteOriginal"] = ai_url

        # Превью
        prev_val = photo.get("preview")
        if prev_val == raw_orig_val and photo.get("cameraOriginal"):
            photo["preview"] = photo["cameraOriginal"]
        else:
            prev_url = _persist_b64_to_disk(clean_id, "preview", prev_val)
            if prev_url:
                photo["preview"] = prev_url
            elif photo.get("cameraOriginal") and not photo.get("preview"):
                photo["preview"] = photo["cameraOriginal"]

        # Удаляем тяжелые дубликаты и историю
        photo.pop("data", None)
        photo.pop("history", None)

        updated_urls[pid] = {
            "preview": photo.get("preview", ""),
            "cameraOriginal": photo.get("cameraOriginal", ""),
            "rawOriginal": photo.get("rawOriginal", ""),
            "croppedBase": photo.get("croppedBase"),
            "aiWhiteOriginal": photo.get("aiWhiteOriginal"),
        }

    # 2. Де-дуплицируем слоты в booksSession до ссылок по ID
    for book in books_session:
        if not isinstance(book, dict):
            continue
        slots = book.get("slots")
        if not isinstance(slots, dict):
            continue
        # Одиночный слот: только cover_front
        val = slots.get("cover_front")
        if isinstance(val, dict) and "id" in val:
            slots["cover_front"] = {"id": val["id"]}
        elif val:
            slots["cover_front"] = None

        # Множественные слоты: cover_back, info_pages, illustrations, mantra_defects
        for s in ("cover_back", "info_pages", "illustrations", "mantra_defects"):
            val = slots.get(s)
            if isinstance(val, list):
                slots[s] = [{"id": item["id"]} for item in val if isinstance(item, dict) and "id" in item]
            elif isinstance(val, dict) and "id" in val:
                slots[s] = [{"id": val["id"]}]
            else:
                slots[s] = []

    # 3. Атомарно сохраняем ультра-компактный JSON на диск
    temp_draft = DRAFT_FILE + ".tmp"
    with open(temp_draft, "w", encoding="utf-8") as f:
        json.dump(draft_data, f, ensure_ascii=False, indent=2)
    os.replace(temp_draft, DRAFT_FILE)

    return updated_urls


def clear_session_draft_storage():
    """Удаляет файл черновика и очищает временные фотографии сессии и неразобранного инбокса."""
    if os.path.exists(DRAFT_FILE):
        try:
            os.remove(DRAFT_FILE)
        except Exception:
            pass
    if os.path.exists(SESSION_PHOTOS_DIR):
        try:
            for fname in os.listdir(SESSION_PHOTOS_DIR):
                if fname.startswith("."):
                    continue
                fpath = os.path.join(SESSION_PHOTOS_DIR, fname)
                if os.path.isfile(fpath) or os.path.islink(fpath):
                    os.remove(fpath)
        except Exception:
            pass
    from config import INBOX_DIR
    if os.path.exists(INBOX_DIR):
        try:
            for fname in os.listdir(INBOX_DIR):
                if fname.startswith(".") or fname.lower() in ("card.png", "card.jpg"):
                    continue
                if fname.startswith("mobile_batch_") or fname.startswith("temp_"):
                    fpath = os.path.join(INBOX_DIR, fname)
                    if os.path.isfile(fpath) or os.path.islink(fpath):
                        os.remove(fpath)
        except Exception:
            pass


def reopen_book_from_vault(article: str) -> Optional[Dict[str, Any]]:
    """
    Восстанавливает сохраненную книгу из storage/books_vault/<article>_* обратно в активную сессию:
    - Считывает book_state.json или запись из catalog.db
    - Восстанавливает слоты с URL к файлам vault и живыми рамками кропа
    - Возвращает структуру книги для отображения в студии
    """
    if not article or not os.path.exists(VAULT_DIR):
        return None

    clean_art = article.strip()
    target_dir = None
    folder_name = None

    for d in os.listdir(VAULT_DIR):
        if d == clean_art or d.startswith(f"{clean_art}_"):
            candidate = os.path.join(VAULT_DIR, d)
            if os.path.isdir(candidate):
                target_dir = candidate
                folder_name = d
                break

    from services.db_service import get_book_from_db
    db_book = get_book_from_db(clean_art) or {}

    if not target_dir:
        if not db_book:
            return None
        # Восстанавливаем книгу из базы данных SQLite (по постоянным ссылкам S3 / Ozon CDN)
        main_url = db_book.get("main_photo_url") or db_book.get("photo_main") or ""
        add_urls_raw = db_book.get("add_photo_urls") or db_book.get("photos_additional") or ""
        add_urls = add_urls_raw.split() if isinstance(add_urls_raw, str) else (add_urls_raw or [])

        def _wrap_proxy(u_val: str) -> str:
            if not u_val:
                return ""
            u_clean = str(u_val).strip()
            if u_clean.startswith("http://") or u_clean.startswith("https://"):
                return f"/api/image_proxy?url={urllib.parse.quote(u_clean, safe='')}"
            return u_clean

        safe_main_url = _wrap_proxy(main_url)
        cf_raw_orig = safe_main_url

        slots = {
            "cover_front": {
                "id": f"cloud_{clean_art}_cover",
                "name": "01_cover_front.jpg",
                "preview": safe_main_url,
                "url": safe_main_url,
                "cameraOriginal": cf_raw_orig,
                "rawOriginal": cf_raw_orig,
                "croppedBase": safe_main_url,
                "isCropped": False,
                "rotation": 0,
            } if main_url else None,
            "cover_back": [],
            "info_pages": [],
            "illustrations": [],
            "mantra_defects": []
        }

        cur_defect_idx = 1
        cur_ill_idx = 1
        cur_cb_idx = 1

        for idx, u in enumerate(add_urls, 1):
            if not u:
                continue
            u_clean = str(u).strip()
            safe_u = _wrap_proxy(u_clean)
            target_slot = classify_filename_to_slot(u_clean)

            # Промо-карточка Ozon (99_card.jpg) не должна загружаться в рабочие слоты книги
            if target_slot == SLOT_CARD:
                continue
            if idx == len(add_urls) and len(add_urls) > 1 and ("card" in u_clean.lower() or u_clean.endswith("card.jpg")):
                continue

            raw_cand = safe_u
            item_obj = {
                "id": f"cloud_{clean_art}_{idx}",
                "name": os.path.basename(u_clean.split("?")[0]) or f"photo_{idx}.jpg",
                "preview": safe_u,
                "url": safe_u,
                "cameraOriginal": raw_cand,
                "rawOriginal": raw_cand,
                "croppedBase": safe_u,
                "isCropped": False,
                "rotation": 0,
            }
            if target_slot == SLOT_DEFECTS:
                slots["mantra_defects"].append(item_obj)
            elif target_slot == SLOT_COVER_BACK:
                slots["cover_back"].append(item_obj)
            elif target_slot == SLOT_INFO_PAGES:
                slots["info_pages"].append(item_obj)
            else:
                slots["illustrations"].append(item_obj)

        return {
            "id": int(time.time() * 1000) % 1000000,
            "article": clean_art,
            "title": db_book.get("title") or "Книга",
            "slots": slots,
            "formData": db_book,
            "isReopened": True,
        }

    # Пробуем загрузить book_state.json
    state_file = os.path.join(target_dir, "book_state.json")
    saved_state = {}
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f_st:
                saved_state = json.load(f_st)
        except Exception:
            saved_state = {}

    # Собираем слоты
    slots = {
        "cover_front": None,
        "cover_back": [],
        "info_pages": [],
        "illustrations": [],
        "mantra_defects": []
    }

    raw_slots = saved_state.get("slots_photos") or db_book.get("slots_photos") or {}
    db_main_url = str(db_book.get("main_photo_url") or "").strip()
    db_add_urls_str = str(db_book.get("add_photo_urls") or "").strip()
    db_add_urls = [u for u in db_add_urls_str.split() if u]

    def _find_cloud_url(filename: str, slot_name: str) -> Optional[str]:
        if slot_name == "cover_front" and db_main_url:
            return db_main_url
        base = os.path.splitext(filename)[0]
        # 1. Точное вхождение имени файла в ссылку на S3
        for u in db_add_urls:
            if base in u or filename in u:
                return u
        # 2. Сопоставление по слоту
        if slot_name == "cover_back":
            for u in db_add_urls:
                if "cover_back" in u or "04_" in u:
                    return u
        elif slot_name == "mantra_defects":
            for u in db_add_urls:
                if "defect" in u or "05_" in u:
                    return u
        return None

    def _make_vault_photo_obj(slot_name: str, filename: str, meta: Optional[dict] = None) -> Optional[Dict[str, Any]]:
        fpath = os.path.join(target_dir, filename)
        if not os.path.exists(fpath):
            return None
        quoted_folder = urllib.parse.quote(folder_name)
        quoted_file = urllib.parse.quote(filename)
        url = f"/vault/{quoted_folder}/{quoted_file}"
        pid = (meta and meta.get("id")) or f"vault_{clean_art}_{filename.replace('.', '_')}"

        # Проверяем наличие сырого исходника в raw_sources/
        raw_source_url = None
        raw_sources_dir = os.path.join(target_dir, "raw_sources")
        if os.path.exists(raw_sources_dir):
            for rf in os.listdir(raw_sources_dir):
                if filename.split(".")[0] in rf or slot_name in rf:
                    raw_source_url = f"/vault/{quoted_folder}/raw_sources/{urllib.parse.quote(rf)}"
                    break

        cam_orig = raw_source_url or url
        s3_cand = _find_cloud_url(filename, slot_name)

        return {
            "id": pid,
            "name": filename,
            "preview": url,
            "url": url,
            "s3_url": s3_cand,
            "is_s3_uploaded": bool(s3_cand),
            "cameraOriginal": cam_orig,
            "rawOriginal": cam_orig,
            "croppedBase": url,
            "isCropped": bool(meta and (meta.get("isCropped") or meta.get("crop_relative") or meta.get("cropRelative"))) or bool(s3_cand),
            "crop_relative": (meta and (meta.get("crop_relative") or meta.get("cropRelative") or meta.get("aiCropRelative"))),
            "rotation": int(meta.get("rotation", 0)) if meta else 0,
            "whiten": meta.get("whiten", 0) if meta else 0,
            "brightness": meta.get("brightness", 0) if meta else 0,
            "contrast": meta.get("contrast", 0) if meta else 0,
            "isFromVault": True,
        }

    # Сканируем все файлы в папке книги и распределяем их по слотам
    seen_files = set()

    # 1. Лицевая обложка (01_cover_front)
    for fname in sorted(os.listdir(target_dir)):
        if fname.lower().endswith(('.jpg', '.jpeg', '.png')) and ('front' in fname.lower() or fname.startswith('01_')):
            cf_meta = raw_slots.get("cover_front") if isinstance(raw_slots.get("cover_front"), dict) else None
            slots["cover_front"] = _make_vault_photo_obj("cover_front", fname, cf_meta)
            seen_files.add(fname)
            break

    # 2. Все остальные файлы
    for fname in sorted(os.listdir(target_dir)):
        if fname in seen_files or fname.startswith(".") or not fname.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue

        # Пропускаем экспортированные файлы Ozon / S3 вида DP-B-XXXXX_1.jpg или DP_B_XXXXX_1.jpg
        clean_prefix = clean_art.replace("-", "_")
        clean_dash = clean_art.replace("_", "-")
        if fname.startswith(clean_art) or fname.startswith(clean_prefix) or fname.startswith(clean_dash):
            continue

        target_slot = classify_filename_to_slot(fname)
        if target_slot == SLOT_CARD:
            continue

        slot_meta = None
        raw_items = raw_slots.get(target_slot)
        if isinstance(raw_items, dict):
            slot_meta = raw_items
        elif isinstance(raw_items, list) and raw_items:
            m_num = re.search(r"(\d+)", fname)
            curr_count = len(slots.get(target_slot, []))
            target_idx = int(m_num.group(1)) - 1 if m_num else curr_count
            if 0 <= target_idx < len(raw_items):
                slot_meta = raw_items[target_idx]
            elif curr_count < len(raw_items):
                slot_meta = raw_items[curr_count]

        p_obj = _make_vault_photo_obj(target_slot, fname, slot_meta)
        if p_obj:
            if target_slot in slots:
                slots[target_slot].append(p_obj)
            else:
                slots["illustrations"].append(p_obj)

    # Формируем итоговый объект книги для сессии
    book_entry = {
        "id": int(time.time() * 1000) % 1000000,
        "article": clean_art,
        "title": db_book.get("title") or saved_state.get("title") or "Книга",
        "slots": slots,
        "formData": db_book,
        "isReopened": True,
    }
    return book_entry



