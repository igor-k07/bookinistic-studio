"""
routes.py: Декларативная регистрация всех API-эндпоинтов системы.
Связывает URL-пути с методами соответствующих контроллеров.
"""

from server.controllers import (
    asset_controller,
    book_controller,
    photo_controller,
    session_controller,
    system_controller,
)
from server.router import Router


def build_router() -> Router:
    """Создает и настраивает главный роутер приложения."""
    router = Router()

    # --- Реестр ассетов и фото-движок V2 (AssetController) ---
    router.post("/api/assets/upload")(asset_controller.upload_assets)
    router.get("/api/assets/list")(asset_controller.list_assets_api)
    router.get("/api/assets/get")(asset_controller.get_asset_api)
    router.post("/api/assets/assign")(asset_controller.assign_slot_api)
    router.post("/api/assets/transform")(asset_controller.transform_asset_api)
    router.post("/api/assets/run_ai")(asset_controller.run_ai_api)
    router.post("/api/assets/delete")(asset_controller.delete_asset_api)
    router.get("/api/storage/stats")(asset_controller.storage_stats_api)
    router.post("/api/storage/cleanup")(asset_controller.cleanup_storage_api)
    router.post("/api/books/reopen")(asset_controller.reopen_book_api)

    # --- Книги и каталог (BookController) ---
    router.get("/api/get_books")(book_controller.get_books)
    router.get("/api/get_next_article")(book_controller.get_next_article)
    router.get("/api/check_article")(book_controller.check_article)
    router.get("/api/get_db_catalog")(book_controller.get_db_catalog)
    router.post("/api/save_book")(book_controller.save_book)
    router.post("/api/books/smart_save")(book_controller.smart_save_book)
    router.post("/api/delete_book_row")(book_controller.delete_book_row)
    router.post("/api/clear_excel")(book_controller.clear_excel)
    router.post("/api/ozon/publish_book")(book_controller.publish_ozon_book)
    router.post("/api/ozon/update_pictures")(book_controller.update_ozon_pictures)

    # --- Фотографии и ИИ (PhotoController) ---
    router.post("/api/ai_recognize_book")(photo_controller.recognize_book)
    router.post("/api/enrich_book")(photo_controller.enrich_book)
    router.post("/api/ai_classify_batch")(photo_controller.classify_batch)
    router.post("/api/ai_process_photo")(photo_controller.process_photo)
    router.post("/api/s3_upload_slot_photo")(photo_controller.upload_slot_photo)

    # --- Мобильные сессии и черновики (SessionController) ---
    router.post("/api/mobile_upload")(session_controller.mobile_upload)
    router.get("/api/check_mobile_event")(session_controller.check_mobile_event)
    router.post("/api/save_session_draft")(session_controller.save_session_draft)
    router.get("/api/get_session_draft")(session_controller.get_session_draft)
    router.post("/api/clear_session_draft")(session_controller.clear_session_draft)

    # --- Система, туннель, Ozon и утилиты (SystemController) ---
    router.get("/api/get_tunnel_url")(system_controller.get_tunnel_url)
    router.get("/api/restart_tunnel")(system_controller.restart_tunnel)
    router.get("/api/references")(system_controller.get_references)
    router.get("/api/load_test_batch")(lambda ctx: {"success": True, "photos": []})
    router.get("/api/db_sync_status")(system_controller.get_sync_status)
    router.post("/api/backup_db")(system_controller.backup_db)
    router.post("/api/restore_db")(system_controller.restore_db)
    router.post("/api/save_key")(system_controller.save_key)
    router.get("/api/get_key")(system_controller.get_key)
    router.get("/api/get_memos")(system_controller.get_memos)
    router.get("/api/open_guide")(system_controller.open_guide)
    router.get("/api/open_ready_folder")(system_controller.open_ready_folder)
    router.get("/api/open_docs_folder")(system_controller.open_docs_folder)
    router.get("/api/reveal_file")(system_controller.reveal_file)
    router.get("/api/download_excel")(system_controller.download_excel)
    router.get("/api/download_photos_zip")(system_controller.download_photos_zip)
    router.post("/api/cleanup_temp")(system_controller.cleanup_temp)

    # --- Ozon Seller API & Smart Cloud Sync ---
    router.get("/api/ozon/status")(system_controller.ozon_status)
    router.get("/api/ozon/task_status")(system_controller.ozon_task_status)
    router.get("/api/ozon/import_status")(system_controller.ozon_import_status)
    router.post("/api/ozon/save_keys")(system_controller.ozon_save_keys)
    router.post("/api/ozon/start_import")(system_controller.ozon_start_import)
    router.post("/api/sync/smart_s3")(system_controller.smart_s3_sync_start)
    router.get("/api/sync/smart_s3/status")(system_controller.smart_s3_sync_status)

    return router

