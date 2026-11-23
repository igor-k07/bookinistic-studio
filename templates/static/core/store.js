/**
 * store.js: Реактивный единый источник истины (Single Source of Truth) Bookinistic Studio.
 * Инкапсулирует состояние всех сессий книг и ассетов в памяти JavaScript.
 * Все мутации данных проходят строго через методы BookStore и уведомляют шину событий EventBus.
 */

(function (window) {
  'use strict';

  class BookStore {
    constructor() {
      this.books = [];
      this.activeId = 1;
      this.isInitialized = false;
    }

    /**
     * Создает чистую структуру книги
     */
    createDefaultBook(id = 1, article = '') {
      return {
        id: Number(id),
        article: article || '',
        title: `Книга #${id}`,
        isEditMode: false,
        isReopened: false,
        isAiRecognizing: false,
        isSavedToExcel: false,
        slots: {
          cover_front: null,
          cover_back: [],
          info_pages: [],
          illustrations: [],
          mantra_defects: []
        },
        formData: {
          article: article || '',
          article_number: '',
          barcode: '',
          isbn: '',
          title: '',
          original_title: '',
          series: '',
          author_cover: '',
          author: '',
          illustrator: '',
          translator: '',
          publisher: '',
          brand: 'Нет бренда',
          year: '',
          country: 'Россия (СССР)',
          pages: '',
          cover_type: 'Твердый переплет',
          paper_type: 'Типографская',
          genre: 'Проза',
          age_limit: '16+',
          target_audience: 'Взрослая',
          condition: 'Хорошая',
          annotation: '',
          hashtags: '',
          price: '350',
          old_price: '490',
          dimensions: '140х215х22',
          weight: '300',
          width: '140',
          length: '215',
          height: '22',
          width_package: '140',
          length_package: '215',
          height_package: '32',
          weight_package: '330',
          auto_package_adder: true,
          template_mode: 'pre2011'
        }
      };
    }

    /**
     * Инициализация хранилища с массивом книг
     */
    init(initialBooks = [], initialActiveId = 1) {
      if (Array.isArray(initialBooks) && initialBooks.length > 0) {
        this.books = initialBooks.map(b => this.normalizeBook(b));
      } else {
        this.books = [this.createDefaultBook(1)];
      }
      this.activeId = Number(initialActiveId) || (this.books[0] ? this.books[0].id : 1);
      this.isInitialized = true;
      this.syncLegacyGlobals();
      this.emit('store:initialized', { activeId: this.activeId, count: this.books.length });
    }

    /**
     * Нормализует структуру книги
     */
    normalizeBook(b) {
      if (!b) return this.createDefaultBook(1);
      const def = this.createDefaultBook(b.id, b.article);
      return {
        ...def,
        ...b,
        slots: { ...def.slots, ...(b.slots || {}) },
        formData: { ...def.formData, ...(b.formData || {}) }
      };
    }

    /**
     * Возвращает активную книгу
     */
    getActiveBook() {
      if (!this.books || this.books.length === 0) {
        return null;
      }
      return this.books.find(b => b.id === this.activeId) || this.books[0] || null;
    }

    /**
     * Возвращает книгу по ID
     */
    getBookById(id) {
      return this.books.find(b => b.id === Number(id)) || null;
    }

    /**
     * Получить весь список книг
     */
    getBooks() {
      return this.books;
    }

    /**
     * Установка значения поля книги
     */
    setField(field, value, bookId = null) {
      const bId = bookId !== null ? Number(bookId) : this.activeId;
      const book = this.getBookById(bId);
      if (!book) return;

      if (!book.formData) book.formData = {};
      const oldValue = book.formData[field];
      book.formData[field] = value;

      if (field === 'article') book.article = value;
      if (field === 'title') book.title = value || `Книга #${book.id}`;

      // Автоматическое определение шаблона при вводе года
      if (field === 'year') {
        const y = parseInt(value, 10);
        if (!isNaN(y) && y > 1000 && y < 2100) {
          book.formData.template_mode = (y <= 2011) ? 'pre2011' : 'post2011';
          if (typeof window.setTemplateMode === 'function') {
            window.setTemplateMode(book.formData.template_mode, false);
          }
        }
      }

      this.syncLegacyGlobals();
      this.emit('book:field_changed', { bookId: bId, field, value, oldValue });
    }

    /**
     * Пакетное обновление полей
     */
    updateFields(fields = {}, bookId = null) {
      const bId = bookId !== null ? Number(bookId) : this.activeId;
      const book = this.getBookById(bId);
      if (!book || !fields) return;

      if (!book.formData) book.formData = {};
      Object.entries(fields).forEach(([k, v]) => {
        if (v !== undefined && v !== null) {
          book.formData[k] = v;
          if (k === 'article') book.article = v;
          if (k === 'title') book.title = v;
        }
      });

      this.syncLegacyGlobals();
      this.emit('book:fields_updated', { bookId: bId, fields });
    }

    /**
     * Назначение фото в слот
     */
    assignSlot(slotName, asset, bookId = null) {
      const bId = bookId !== null ? Number(bookId) : this.activeId;
      const book = this.getBookById(bId);
      if (!book) return;

      if (!book.slots) book.slots = {};
      if (slotName === 'cover_front') {
        book.slots.cover_front = asset;
      } else {
        if (!Array.isArray(book.slots[slotName])) book.slots[slotName] = [];
        if (asset && !book.slots[slotName].some(x => x && x.id === asset.id)) {
          book.slots[slotName].push(asset);
        }
      }

      this.syncLegacyGlobals();
      this.emit('book:slots_changed', { bookId: bId, slotName, asset });
    }

    /**
     * Установка слотов книги целиком (например, после сохранения или загрузки из vault)
     */
    setSlots(slots = {}, bookId = null) {
      const bId = bookId !== null ? Number(bookId) : this.activeId;
      const book = this.getBookById(bId);
      if (!book) return;

      book.slots = slots;
      this.syncLegacyGlobals();
      this.emit('book:slots_updated', { bookId: bId, slots });
    }

    /**
     * Очистка слотов книги
     */
    clearSlots(bookId = null) {
      const bId = bookId !== null ? Number(bookId) : this.activeId;
      const book = this.getBookById(bId);
      if (!book) return;

      book.slots = {
        cover_front: null,
        cover_back: [],
        info_pages: [],
        illustrations: [],
        mantra_defects: []
      };

      this.syncLegacyGlobals();
      this.emit('book:slots_cleared', { bookId: bId });
    }

    /**
     * Мгновенное переключение активной книги
     */
    switchActiveBook(newId) {
      const targetId = Number(newId);
      if (this.activeId === targetId) return;
      const targetBook = this.getBookById(targetId);
      if (!targetBook) return;

      const previousId = this.activeId;
      this.activeId = targetId;

      this.syncLegacyGlobals();
      this.emit('book:switched', { previousId, activeId: targetId, book: targetBook });
    }

    /**
     * Добавление новой книги в сессию
     */
    addBook(article = '') {
      const maxId = this.books.reduce((max, b) => Math.max(max, Number(b.id) || 0), 0);
      const nextId = maxId + 1;
      const newBook = this.createDefaultBook(nextId, article);
      this.books.push(newBook);
      this.switchActiveBook(nextId);
      this.emit('book:added', { book: newBook, totalCount: this.books.length });
      return newBook;
    }

    /**
     * Удаление книги из сессии (допускается закрытие всех вкладок до 0)
     */
    removeBook(id) {
      const targetId = Number(id);
      this.books = this.books.filter(b => b.id !== targetId);
      if (this.activeId === targetId) {
        this.activeId = this.books.length > 0 ? this.books[0].id : null;
      }

      this.syncLegacyGlobals();
      this.emit('book:removed', { removedId: targetId, activeId: this.activeId });
      return true;
    }

    /**
     * Закрыть сразу все открытые вкладки книг (очистить сессию до 0)
     */
    removeAllBooks() {
      this.books = [];
      this.activeId = null;
      this.syncLegacyGlobals();
      this.emit('book:all_removed', {});
      return true;
    }

    /**
     * Применение данных от Gemini AI без затирания ручных полей
     */
    applyAiData(aiResult, bookId = null) {
      const bId = bookId !== null ? Number(bookId) : this.activeId;
      const book = this.getBookById(bId);
      if (!book || !aiResult) return;

      const updates = {};
      const fields = [
        'title', 'author', 'year', 'publisher', 'pages', 'cover_type',
        'paper_type', 'genre', 'age_limit', 'annotation', 'condition'
      ];

      fields.forEach(f => {
        if (aiResult[f] && !book.formData[f]) {
          updates[f] = aiResult[f];
        }
      });

      this.updateFields(updates, bId);
      this.emit('book:ai_applied', { bookId: bId, updates });
    }

    /**
     * Синхронизация с глобальными переменными для 100% обратной совместимости
     */
    syncLegacyGlobals() {
      if (typeof window === 'undefined') return;
      window.booksSession = this.books;
      window.activeBookId = this.activeId;
    }

    /**
     * Оповещение через шину событий EventBus
     */
    emit(event, data) {
      if (window.EventBus && typeof window.EventBus.emit === 'function') {
        window.EventBus.emit(event, data);
      }
    }
  }

  // Создаем единый экземпляр хранилища
  window.BookStore = new BookStore();
  // Инициализация дефолтной книгой #1
  window.BookStore.init();

})(window);
