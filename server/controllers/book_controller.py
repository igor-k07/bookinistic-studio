"""
book_controller.py: Контроллер работы с книгами (сохранение, список, удаление, артикулы).
"""

from typing import Any, Dict

from core.use_cases.save_book import SaveBookUseCase
from server.router import RequestContext
from services.db_service import (
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
    """POST /api/save_book: Сохранение книги через UseCase."""
    data = ctx.get_json()
    return save_book_use_case.execute(data)


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
    """GET /api/get_next_article: Следующий уникальный артикул DP-B-XXXXX."""
    return {"success": True, "article": get_next_article_number()}


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


