# 🗺️ Дорожная карта реализации Bookinistic Studio (Roadmap)

В этой папке собраны утвержденные архитектурные и технические планы реализации всех блоков системы, согласованные в ходе проектирования.

---

## 📌 Статус выполнения блоков

| Шаг | Название блока | Описание задачи | Статус | Документ |
| :---: | :--- | :--- | :---: | :--- |
| **Шаг 1** | **Оптимизация фото-конвейера** | Селективный `rembg`, защита белых обложек (`OpenCV`), свободный `Cropper` (+3.5%) с опцией 3:4, 4 пресета студии, удаление лишних кнопок. | 🟡 Готов к разработке | [STEP_1_PHOTO_PIPELINE.md](file:///Users/igor/Projects/real_projects/bookinistic/docs/roadmap/STEP_1_PHOTO_PIPELINE.md) |
| **Шаг 2** | **Интеллектуальное распознавание** | Сжатие превью для Gemini Vision, раздельный режим FantLab с бейджем подтверждения, подбор вариантов по закрытым справочникам Ozon (`catalog.db`). | ⚪ Запланирован | [STEP_2_AI_AND_CATALOG.md](file:///Users/igor/Projects/real_projects/bookinistic/docs/roadmap/STEP_2_AI_AND_CATALOG.md) |
| **Шаг 3** | **Упреждающая выгрузка в S3 CDN** | Фоновая предзагрузка фото в Yandex S3 при назначении в слот. Мгновенная запись книги за 0.2 сек. | ⚪ Запланирован | [STEP_3_S3_BACKGROUND.md](file:///Users/igor/Projects/real_projects/bookinistic/docs/roadmap/STEP_3_S3_BACKGROUND.md) |
| **Шаг 4** | **Очистка диска и памяти Mac** | Безопасная очистка временных фото по кнопке в конце рабочего дня. Отказ от Base64 в DOM в пользу Blob/URL. | ⚪ Запланирован | [STEP_4_DISK_MEMORY_CLEANUP.md](file:///Users/igor/Projects/real_projects/bookinistic/docs/roadmap/STEP_4_DISK_MEMORY_CLEANUP.md) |
| **Шаг 5** | **Интеграция с Ozon Seller API** | Гибридная публикация: 1 клик для отдельной книги или пачкой для всей сессии. Поллинг статуса модерации Ozon + резервный Excel. | ⚪ Запланирован | [STEP_5_OZON_SELLER_API.md](file:///Users/igor/Projects/real_projects/bookinistic/docs/roadmap/STEP_5_OZON_SELLER_API.md) |
| **Шаг 6** | **Мобильная студия съёмки** | Крупная разметка ролей кадров в 1 тап, тач-перенос фото между книгами, кэширование в IndexedDB от выгрузки вкладок. | ⚪ Запланирован | [STEP_6_MOBILE_STUDIO.md](file:///Users/igor/Projects/real_projects/bookinistic/docs/roadmap/STEP_6_MOBILE_STUDIO.md) |

---

## 📑 Сводный документ

Полный архитектурный обзор всех этапов в одном месте доступен в:  
👉 **[MASTER_ROADMAP.md](file:///Users/igor/Projects/real_projects/bookinistic/docs/roadmap/MASTER_ROADMAP.md)**
