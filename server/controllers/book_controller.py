"""
book_controller.py: Контроллер работы с книгами (сохранение, список, удаление, артикулы).
"""

from typing import Any, Dict

from core.use_cases.save_book import SaveBookUseCase
from server.router import RequestContext
from services.db_service import (
    check_article_exists,
    delete_book_from_db,
    get_all_books_from_db,
    get_next_article_number,
)
from services.excel_service import (
    clear_excel_table,
    delete_book_from_excel,
    get_current_books,
)

save_book_use_case = SaveBookUseCase()


def save_book(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/save_book: Сохранение книги через UseCase с защитой от перезаписи."""
    data = ctx.get_json()
    try:
        return save_book_use_case.execute(data)
    except ValueError as val_err:
        err_msg = str(val_err)
        return {
            "success": False,
            "error": err_msg,
            "code": "ARTICLE_ALREADY_EXISTS" if "уже занят" in err_msg else "VALIDATION_ERROR",
            "suggested_article": get_next_article_number(verify_ozon=True),
        }


def check_article(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/check_article: Проверка существования артикула в БД и на Ozon."""
    art = ctx.get_query("article", "").strip()
    if not art:
        return {"success": False, "error": "Не передан артикул"}
    res = check_article_exists(art, check_ozon=True)
    res["success"] = True
    res["suggested_next_article"] = get_next_article_number(verify_ozon=True)
    return res


def get_books(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/get_books: Список книг текущей сессии."""
    mode = ctx.get_query("mode", "pre2011")
    pre_books = get_current_books("pre2011")
    post_books = get_current_books("post2011")
    current_list = pre_books if mode == "pre2011" else post_books
    return {
        "success": True,
        "mode": mode,
        "books": current_list,
        "pre2011_count": len(pre_books),
        "post2011_count": len(post_books),
        "total": len(pre_books) + len(post_books),
    }


def get_next_article(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/get_next_article: Следующий гарантированно свободный артикул DP-B-XXXXX."""
    verify = ctx.get_query("verify_ozon", "0") == "1"
    return {"success": True, "article": get_next_article_number(verify_ozon=verify)}


def get_db_catalog(ctx: RequestContext) -> Dict[str, Any]:
    """GET /api/get_db_catalog: Полный каталог книг из базы данных SQLite."""
    mode = ctx.get_query("mode")
    status = ctx.get_query("status")
    search = ctx.get_query("search")
    db_books = get_all_books_from_db(mode=mode, status=status, search=search)
    return {
        "success": True,
        "count": len(db_books),
        "books": db_books,
    }


def delete_book_row(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/delete_book_row: Удаление книги из БД и Excel."""
    body = ctx.get_json()
    article = body.get("article", "")
    mode = body.get("mode", "pre2011")
    if not article:
        raise ValueError("Не указан артикул книги для удаления")

    try:
        delete_book_from_db(article)
    except Exception as db_e:
        print(f"⚠️ [BookController] Ошибка удаления из БД: {db_e}", flush=True)

    return delete_book_from_excel(article, mode)


def clear_excel(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/clear_excel: Очистка таблицы Excel."""
    body = ctx.get_json()
    mode = body.get("mode", "pre2011")
    return clear_excel_table(mode)


def publish_ozon_book(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/ozon/publish_book: Прямая выгрузка книги в Ozon Seller API."""
    import services.ozon_service as ozon_service
    body = ctx.get_json()
    ok, res = ozon_service.publish_product_to_ozon(body)
    if ok:
        return {"success": True, "result": res}
    return {"success": False, "error": str(res)}


def update_ozon_pictures(ctx: RequestContext) -> Dict[str, Any]:
    """POST /api/ozon/update_pictures: Точечное обновление фото товара на Ozon без перезаливки таблицы."""
    import services.ozon_service as ozon_service
    from services.s3_service import upload_book_photos
    from services.db_service import get_book_from_db, save_book_to_db

    body = ctx.get_json()
    article = (body.get("article") or "").strip()
    title = (body.get("title") or "").strip()
    slots_photos = body.get("slots_photos") or body.get("slots")
    primary_image = (body.get("primary_image") or body.get("main_photo_url") or "").strip()
    images = list(body.get("images") or [])
    add_urls = body.get("add_photo_urls")
    if isinstance(add_urls, str):
        for u in add_urls.split():
            if u.strip() and u.strip() not in images:
                images.append(u.strip())

    if not article:
        raise ValueError("Не передан артикул товара")

    # Если переданы слоты (из активного редактора книги), ВСЕГДА выполняем
    # выгрузку актуальных отредактированных фото в S3 с force_upload=True,
    # чтобы запечь свет, контраст, белый фон и получить свежие ссылки с версией ?v=...
    if slots_photos:
        from services.vault_service import save_book_vault_photos
        try:
            save_book_vault_photos(article, title, slots_photos)
        except Exception as e_vault:
            print(f"⚠️ Ошибка обновления локального vault в update_ozon_pictures: {e_vault}")

        s3_main, s3_adds = upload_book_photos(article, title, slots_photos, force_upload=True)
        if s3_main:
            primary_image = s3_main
        if s3_adds:
            images = [u for u in s3_adds.split() if u]

    # Если всё ещё нет primary_image, проверяем базу данных catalog.db
    if not primary_image:
        db_book = get_book_from_db(article)
        if db_book:
            primary_image = db_book.get("main_photo_url") or db_book.get("photo_main") or ""
            if not images and db_book.get("add_photo_urls"):
                images = db_book["add_photo_urls"].split()

    if not primary_image:
        raise ValueError("Не найдено главное фото (обложка) для товара " + article)

    ok, res = ozon_service.update_ozon_product_pictures(article, primary_image, images)
    if ok:
        try:
            db_b = get_book_from_db(article) or {"article": article}
            db_b["main_photo_url"] = primary_image
            db_b["add_photo_urls"] = " ".join(images)
            if title and not db_b.get("title"):
                db_b["title"] = title
            save_book_to_db(db_b, sync_s3=False)
        except Exception as e_db:
            print(f"⚠️ Ошибка обновления ссылок в catalog.db: {e_db}")

        task_id = (res if isinstance(res, dict) else {}).get("task_id")
        return {"success": True, "result": res, "task_id": task_id, "primary_image": primary_image, "images": images}
    return {"success": False, "error": str(res)}


def smart_save_book(ctx: RequestContext) -> Dict[str, Any]:
    """
    POST /api/books/smart_save: Единая умная синхронизация существующей книги на Ozon.
    Обновляет фото (S3 + локальный кэш), SQLite catalog.db и отправляет обновления в Ozon API.
    """
    import services.ozon_service as ozon_service
    from services.s3_service import upload_book_photos
    from services.vault_service import save_book_vault_photos
    from services.db_service import get_book_from_db, save_book_to_db

    body = ctx.get_json()
    article = (body.get("article") or "").strip()
    if not article:
        raise ValueError("Не передан артикул товара")

    form_data = dict(body.get("formData") or {})
    title = (form_data.get("title") or body.get("title") or "").strip()
    slots_photos = body.get("slots_photos") or body.get("slots")

    # 1. Загружаем текущую запись из базы, чтобы смерджить
    existing_book = get_book_from_db(article) or {}
    merged_data = {**existing_book, **form_data, "article": article}
    if title:
        merged_data["title"] = title

    photos_updated = False
    pictures_res = None
    pictures_task_id = None
    s3_main_url = merged_data.get("main_photo_url")
    s3_add_urls = merged_data.get("add_photo_urls") or ""

    # 2. Если переданы слоты с фото — сохраняем в vault и заливаем в S3 с force_upload=True
    if slots_photos:
        try:
            save_book_vault_photos(article, title, slots_photos)
        except Exception as e_v:
            print(f"⚠️ Ошибка обновления локального vault в smart_save: {e_v}")

        new_main, new_adds = upload_book_photos(article, title, slots_photos, force_upload=True)
        if new_main:
            s3_main_url = new_main
            merged_data["main_photo_url"] = new_main
            photos_updated = True
        if new_adds is not None:
            s3_add_urls = new_adds
            merged_data["add_photo_urls"] = new_adds
            photos_updated = True

        merged_data["slots_photos"] = slots_photos

    # 3. Сохраняем актуальные данные в SQLite catalog.db
    save_book_to_db(merged_data, sync_s3=False)

    # 3.1. Синхронизируем обновленную книгу с официальной таблицей Excel Ozon
    try:
        from services.excel_service import sync_book_to_excel
        sync_book_to_excel(merged_data)
    except Exception as e_xl:
        print(f"⚠️ Ошибка синхронизации с Excel в smart_save: {e_xl}", flush=True)

    # 4. Обновление фото на Ozon (если фото обновились)
    if photos_updated and s3_main_url:
        images_list = [u for u in s3_add_urls.split() if u]
        ok_pic, pic_res = ozon_service.update_ozon_product_pictures(article, s3_main_url, images_list)
        if ok_pic:
            pictures_res = pic_res
            pictures_task_id = (pic_res if isinstance(pic_res, dict) else {}).get("task_id")
        else:
            print(f"⚠️ Ошибка обновления фото на Ozon в smart_save: {pic_res}")

    # 5. Обновление карточки товара (текст, цена, габариты) в Ozon
    product_res = None
    product_task_id = None
    try:
        ok_prod, prod_res = ozon_service.publish_product_to_ozon(merged_data)
        if ok_prod:
            product_res = prod_res
            product_task_id = (prod_res if isinstance(prod_res, dict) else {}).get("task_id")
        else:
            print(f"⚠️ Ошибка обновления карточки товара в Ozon: {prod_res}")
    except Exception as e_oz:
        print(f"⚠️ Сбой publish_product_to_ozon в smart_save: {e_oz}")

    return {
        "success": True,
        "article": article,
        "title": title,
        "photos_updated": photos_updated,
        "pictures_task_id": pictures_task_id,
        "product_task_id": product_task_id,
        "main_photo_url": s3_main_url,
        "add_photo_urls": s3_add_urls,
        "message": f"Книга {article} успешно сохранена и синхронизирована с Ozon",
    }



