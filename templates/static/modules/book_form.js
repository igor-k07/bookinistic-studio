/**
 * book_form.js: Декларативная привязка формы карточки книги (data-field) к BookStore.
 * Устраняет разрозненные вызовы document.getElementById(...) и обеспечивает двустороннюю реактивную синхронизацию.
 * Работает как в браузере (window.BookForm), так и в модульных тестах Node.js.
 */

(function (global) {
  'use strict';

  const DEFAULT_CONTAINER = '#ozonFormContainer';

  const FORM_FIELD_KEYS = [
    'article', 'article_number', 'barcode', 'isbn', 'title', 'original_title', 'series',
    'author_cover', 'author', 'illustrator', 'translator', 'publisher', 'brand', 'year',
    'country', 'pages', 'cover_type', 'paper_type', 'genre', 'age_limit', 'target_audience',
    'condition', 'annotation', 'hashtags', 'price', 'old_price', 'dimensions', 'weight',
    'width', 'length', 'height', 'auto_package_adder',
    'width_package', 'length_package', 'height_package', 'weight_package'
  ];

  class BookForm {
    constructor() {
      this.container = null;
      this.fieldsMap = new Map(); // fieldName -> Element
      this.isUpdatingFromStore = false;
      this.initialized = false;
    }

    /**
     * Инициализация привязки формы к DOM и EventBus
     */
    init(containerSelector = DEFAULT_CONTAINER) {
      if (typeof document === 'undefined') return;
      this.container = document.querySelector(containerSelector) || document;
      this.cacheFields();
      this.bindDOMEvents();
      this.bindStoreEvents();
      this.initialized = true;
    }

    /**
     * Поиск и кеширование элементов формы по data-field или id
     */
    cacheFields() {
      this.fieldsMap.clear();
      if (!this.container) return;

      const elements = this.container.querySelectorAll('input, select, textarea');
      elements.forEach(el => {
        const fieldName = el.getAttribute('data-field') || el.id;
        if (fieldName) {
          // Сопоставление camelCase или snake_case для autoPackageAdder
          const normalizedKey = (fieldName === 'autoPackageAdder') ? 'auto_package_adder' : fieldName;
          if (FORM_FIELD_KEYS.includes(normalizedKey)) {
            this.fieldsMap.set(normalizedKey, el);
          }
        }
      });
    }

    /**
     * Делегирование событий ввода (input, change) от пользователя в BookStore
     */
    bindDOMEvents() {
      if (!this.container) return;

      this.container.addEventListener('input', (e) => this.handleFieldInput(e));
      this.container.addEventListener('change', (e) => this.handleFieldChange(e));
    }

    handleFieldInput(e) {
      if (this.isUpdatingFromStore) return;
      const target = e.target;
      if (!target || !target.matches('input, select, textarea')) return;

      const rawField = target.getAttribute('data-field') || target.id;
      const fieldName = (rawField === 'autoPackageAdder') ? 'auto_package_adder' : rawField;
      if (!fieldName || !FORM_FIELD_KEYS.includes(fieldName)) return;

      const value = (target.type === 'checkbox') ? target.checked : target.value;
      if (global.BookStore) {
        global.BookStore.setField(fieldName, value);
      }
    }

    handleFieldChange(e) {
      if (this.isUpdatingFromStore) return;
      const target = e.target;
      if (!target || !target.matches('input, select, textarea')) return;

      const rawField = target.getAttribute('data-field') || target.id;
      const fieldName = (rawField === 'autoPackageAdder') ? 'auto_package_adder' : rawField;
      if (!fieldName || !FORM_FIELD_KEYS.includes(fieldName)) return;

      const value = (target.type === 'checkbox') ? target.checked : target.value;
      if (global.BookStore) {
        global.BookStore.setField(fieldName, value);
      }
    }

    /**
     * Подписка на события хранилища BookStore через шину событий EventBus
     */
    bindStoreEvents() {
      if (!global.EventBus) return;

      global.EventBus.on('book:switched', ({ book }) => {
        if (book && book.formData) {
          this.populateForm(book.formData, { force: true });
        }
      });

      global.EventBus.on('book:field_changed', ({ bookId, field, value }) => {
        if (global.BookStore && bookId === global.BookStore.activeId) {
          this.setFieldValue(field, value);
        }
      });

      global.EventBus.on('book:fields_updated', ({ bookId, fields }) => {
        if (global.BookStore && bookId === global.BookStore.activeId) {
          this.populateForm(fields, { partial: true });
        }
      });
    }

    /**
     * Чтение всех значений полей формы в чистый объект данных
     */
    readForm() {
      const data = {};
      this.fieldsMap.forEach((el, field) => {
        if (el.type === 'checkbox') {
          data[field] = el.checked;
        } else {
          data[field] = el.value !== undefined ? el.value : '';
        }
      });
      return data;
    }

    /**
     * Заполнение элементов формы из переданного объекта данных
     */
    populateForm(data = {}, options = {}) {
      if (!data) return;
      this.isUpdatingFromStore = true;
      try {
        const activeEl = (typeof document !== 'undefined') ? document.activeElement : null;

        Object.entries(data).forEach(([field, val]) => {
          let el = this.fieldsMap.get(field);
          if (!el && typeof document !== 'undefined') {
            el = document.getElementById(field);
          }
          if (!el) return;

          // Не перезаписываем инпут, если пользователь прямо сейчас печатает в нем,
          // если явно не указана опция force
          if (activeEl === el && !options.force) return;

          if (el.type === 'checkbox') {
            el.checked = Boolean(val);
          } else {
            const strVal = (val !== undefined && val !== null) ? String(val) : '';
            // Защита от случайной сериализации [object Object]
            if (strVal.includes('[object')) return;
            if (el.value !== strVal) {
              el.value = strVal;
              if (options.highlight) {
                el.classList.add('field-updated');
                setTimeout(() => el.classList.remove('field-updated'), 1200);
              }
            }
          }
        });
      } finally {
        this.isUpdatingFromStore = false;
      }
    }

    /**
     * Установка значения для отдельного поля формы
     */
    setFieldValue(field, value, options = {}) {
      let el = this.fieldsMap.get(field);
      if (!el && typeof document !== 'undefined') {
        el = document.getElementById(field);
      }
      if (!el) return;

      const activeEl = (typeof document !== 'undefined') ? document.activeElement : null;
      if (activeEl === el && !options.force) return;

      this.isUpdatingFromStore = true;
      try {
        if (el.type === 'checkbox') {
          el.checked = Boolean(value);
        } else {
          const strVal = (value !== undefined && value !== null) ? String(value) : '';
          if (el.value !== strVal) {
            el.value = strVal;
            if (options.highlight) {
              el.classList.add('field-updated');
              setTimeout(() => el.classList.remove('field-updated'), 1200);
            }
          }
        }
      } finally {
        this.isUpdatingFromStore = false;
      }
    }

    /**
     * Очистка полей формы к значениям по умолчанию
     */
    clearForm(defaults = {}) {
      this.isUpdatingFromStore = true;
      try {
        this.fieldsMap.forEach((el, field) => {
          if (defaults[field] !== undefined) {
            if (el.type === 'checkbox') el.checked = Boolean(defaults[field]);
            else el.value = defaults[field];
          } else {
            if (el.type === 'checkbox') el.checked = false;
            else el.value = '';
          }
        });
      } finally {
        this.isUpdatingFromStore = false;
      }
    }
  }

  const bookFormInstance = new BookForm();

  if (typeof document !== 'undefined') {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', () => bookFormInstance.init());
    } else {
      bookFormInstance.init();
    }
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { BookForm, bookFormInstance, FORM_FIELD_KEYS };
  }
  if (typeof global !== 'undefined') {
    global.BookForm = bookFormInstance;
    global.FORM_FIELD_KEYS = FORM_FIELD_KEYS;
  }
})(typeof window !== 'undefined' ? window : global);
