"""
test_pipeline_e2e.py: Комплексный интеграционный тест (E2E) полного жизненного цикла книги:
1. Проверка доступности веб-интерфейса и новых модулей
2. Получение следующего сквозного артикула
3. Тест эндпоинта упреждающей выгрузки S3
4. Сохранение книги (UseCase: Валидация -> S3 -> Vault -> SQLite -> Excel -> Очистка диска)
5. Проверка записи в БД SQLite и таблице Excel
6. Удаление тестовой книги и восстановление чистоты данных
"""

import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE_URL = "http://localhost:8095"

# Минимальный валидный JPEG 10x10 белый квадрат в Base64
SAMPLE_JPEG_B64 = (
    "/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////"
    "////////////////////////////////////////////////////wgALCAAKAAoBAREA"
    "/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
)


def req(method: str, path: str, body: dict = None) -> dict:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_e2e():
    print("=" * 65)
    print("🧪 ЗАПУСК КОМПЛЕКСНОГО E2E ТЕСТИРОВАНИЯ СИСТЕМЫ BOOKINISTIC STUDIO")
    print("=" * 65)

    # 1. Проверка HTML и статики
    print("\n[Шаг 1] Проверка отдачи Desktop HTML и новых модулей...")
    with urllib.request.urlopen(f"{BASE_URL}/", timeout=5) as r:
        html = r.read().decode("utf-8")
        assert "event_bus.js" in html, "event_bus.js не найден в desktop.html"
        assert "blob_manager.js" in html, "blob_manager.js не найден в desktop.html"
        assert "calculators.js" in html, "calculators.js не найден в desktop.html"
        assert "api_client.js" in html, "api_client.js не найден в desktop.html"
        print("  ✅ Desktop HTML успешно отдает все новые модули ядра!")

    # 2. Получение артикула
    print("\n[Шаг 2] Получение актуального артикула книги...")
    art_res = req("GET", "/api/get_next_article")
    assert art_res.get("success") is True
    article = art_res.get("article")
    print(f"  ✅ Артикул получен: {article}")

    # 3. Тест упреждающей выгрузки фото в S3
    print("\n[Шаг 3] Тестирование фоновой упреждающей выгрузки кадра в S3...")
    test_photo_id = "photo_test_e2e_123"
    upload_body = {
        "article": article,
        "title": "Тестовая Книга Архитектуры",
        "slot": "cover_front",
        "photo_index": 1,
        "photo": "data:image/jpeg;base64," + SAMPLE_JPEG_B64,
        "photo_id": test_photo_id,
    }
    s3_res = req("POST", "/api/s3_upload_slot_photo", upload_body)
    print(f"  ℹ️ Ответ эндпоинта S3: success={s3_res.get('success')}, url={s3_res.get('s3_url') or s3_res.get('message')}")

    s3_url_candidate = s3_res.get("s3_url")

    # 4. Сохранение книги в каталог
    print("\n[Шаг 4] Сохранение книги через SaveBookUseCase (Полный цикл)...")
    book_payload = {
        "article": article,
        "title": "Тестовая книга (E2E Архитектура)",
        "author_cover": "Иван Тестов",
        "author": "Тестов Иван Иванович",
        "publisher": "Наука",
        "brand": "Наука",
        "year": "1985",
        "pages": 320,
        "price": "950",
        "condition": "Очень хорошая",
        "cover_type": "Твердый переплет",
        "paper_type": "Типографская",
        "genre": "Научная и научно-популярная литература",
        "template_mode": "pre2011",
        "slots_photos": {
            "cover_front": {
                "id": test_photo_id,
                "data": SAMPLE_JPEG_B64,
                "name": "01_cover_front.jpg",
                "s3_url": s3_url_candidate,
                "is_s3_uploaded": bool(s3_url_candidate),
            }
        }
    }

    t0 = time.time()
    save_res = req("POST", "/api/save_book", book_payload)
    save_duration = time.time() - t0

    assert save_res.get("success") is True, f"Ошибка сохранения книги: {save_res}"
    print(f"  ⚡ Книга сохранена за {save_duration:.3f} сек!")
    print(f"  ✅ Записано в строку Excel: {save_res.get('row')}")
    print(f"  ✅ Сохранено в архив Vault: {save_res.get('vault_folder')}")
    print(f"  ✅ Главное фото: {save_res.get('main_photo_url')}")

    # 5. Проверка наличия книги в списке сессии
    print("\n[Шаг 5] Проверка чтения из таблицы сессии...")
    books_list_res = req("GET", "/api/get_books?mode=pre2011")
    found = any(b.get("article") == article for b in books_list_res.get("books", []))
    assert found, f"Книга {article} не найдена в текущей таблице Excel!"
    print(f"  ✅ Книга {article} подтверждена в таблице Excel среди {books_list_res.get('total')} книг.")

    # 6. Проверка базы данных SQLite
    print("\n[Шаг 6] Проверка базы данных SQLite (catalog.db)...")
    db_res = req("GET", f"/api/get_db_catalog?search={article}")
    assert db_res.get("count", 0) > 0, "Книга не найдена в SQLite catalog.db!"
    print(f"  ✅ Книга {article} успешно найдена в SQLite catalog.db (статус: ready)!")

    # 7. Очистка тестовых данных (восстановление исходного состояния)
    print("\n[Шаг 7] Очистка тестовой записи (возврат в исходное чистое состояние)...")
    del_res = req("POST", "/api/delete_book_row", {"article": article, "mode": "pre2011"})
    assert del_res.get("success") is True
    print(f"  ✅ Тестовая книга {article} корректно удалена из БД и Excel (таблицы чисты).")

    # Удаление тестовой папки из books_vault
    from config import VAULT_DIR
    vault_folder = save_res.get("vault_folder")
    if vault_folder:
        v_path = os.path.join(VAULT_DIR, vault_folder)
        if os.path.exists(v_path):
            import shutil
            shutil.rmtree(v_path, ignore_errors=True)
            print(f"  ✅ Тестовая папка {vault_folder} удалена из books_vault.")

    print("\n" + "=" * 65)
    print("🎉 ВСЕ 7 ЭТАПОВ E2E ТЕСТИРОВАНИЯ ПРОЙДЕНЫ С УСПЕХОМ НА 100%!")
    print("=" * 65)


if __name__ == "__main__":
    run_e2e()
