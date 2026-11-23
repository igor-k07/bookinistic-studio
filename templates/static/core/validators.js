/**
 * validators.js: Чистые функции валидации данных книг и правил Ozon API.
 * Инкапсулирует бизнес-правила (ISBN-10/13, режимы pre2011/post2011, обязательные поля Ozon).
 * Работает как в браузере (window.BookValidators), так и в Node.js.
 */

(function (global) {
  'use strict';

  /**
   * Определение режима карточки (до/после 2011 г.) по году издания.
   * До 2011 года: ISBN необязателен (букинистика).
   * После 2011 года: ISBN строго обязателен для Ozon.
   */
  function resolveTemplateMode(year) {
    const y = parseInt(year, 10);
    if (isNaN(y) || y <= 0) return 'pre2011';
    return y <= 2011 ? 'pre2011' : 'post2011';
  }

  /**
   * Проверка контрольной суммы ISBN-10.
   * Формат: 9 цифр + 1 контрольный символ (0-9 или X).
   */
  function isValidIsbn10(cleanIsbn) {
    if (!/^\d{9}[\dX]$/i.test(cleanIsbn)) return false;
    let sum = 0;
    for (let i = 0; i < 9; i++) {
      sum += parseInt(cleanIsbn[i], 10) * (10 - i);
    }
    const lastChar = cleanIsbn[9].toUpperCase();
    const lastVal = lastChar === 'X' ? 10 : parseInt(lastChar, 10);
    sum += lastVal;
    return sum % 11 === 0;
  }

  /**
   * Проверка контрольной суммы ISBN-13 (GS1 EAN-13).
   * Формат: 13 цифр.
   */
  function isValidIsbn13(cleanIsbn) {
    if (!/^\d{13}$/.test(cleanIsbn)) return false;
    let sum = 0;
    for (let i = 0; i < 12; i++) {
      const d = parseInt(cleanIsbn[i], 10);
      sum += (i % 2 === 0) ? d : d * 3;
    }
    const checkDigit = (10 - (sum % 10)) % 10;
    return parseInt(cleanIsbn[12], 10) === checkDigit;
  }

  /**
   * Конвертация валидного ISBN-10 в ISBN-13.
   */
  function convertIsbn10To13(cleanIsbn10) {
    if (!isValidIsbn10(cleanIsbn10)) return null;
    const base12 = '978' + cleanIsbn10.slice(0, 9);
    let sum = 0;
    for (let i = 0; i < 12; i++) {
      const d = parseInt(base12[i], 10);
      sum += (i % 2 === 0) ? d : d * 3;
    }
    const check = (10 - (sum % 10)) % 10;
    return `${base12}${check}`;
  }

  /**
   * Комплексная валидация ISBN с учетом года издания книги.
   * @param {string} isbn - строка ISBN (может содержать дефисы и пробелы)
   * @param {number|string} [year] - год издания книги
   * @returns {{ isValid: boolean, isRequired: boolean, normalized: string, isIsbn10: boolean, isIsbn13: boolean, isbn13Converted?: string, error?: string, message?: string }}
   */
  function validateIsbn(isbn, year) {
    const raw = String(isbn || '').trim();
    const clean = raw.replace(/[\s-]/g, '');
    const yInt = parseInt(year, 10);
    const isPre2011 = (!isNaN(yInt) && yInt > 0) ? (yInt <= 2011) : true;

    // Пустой ISBN
    if (!clean) {
      if (isPre2011) {
        return {
          isValid: true,
          isRequired: false,
          normalized: '',
          isIsbn10: false,
          isIsbn13: false,
          message: 'Для книг до 2011 года ISBN не обязателен',
        };
      }
      return {
        isValid: false,
        isRequired: true,
        normalized: '',
        isIsbn10: false,
        isIsbn13: false,
        error: 'Для книг после 2011 года ISBN обязателен',
      };
    }

    // Проверка ISBN-10
    if (clean.length === 10) {
      if (isValidIsbn10(clean)) {
        return {
          isValid: true,
          isRequired: !isPre2011,
          normalized: clean.toUpperCase(),
          isIsbn10: true,
          isIsbn13: false,
          isbn13Converted: convertIsbn10To13(clean),
        };
      }
      return {
        isValid: false,
        isRequired: !isPre2011,
        normalized: clean,
        isIsbn10: true,
        isIsbn13: false,
        error: 'Неверная контрольная сумма ISBN-10',
      };
    }

    // Проверка ISBN-13
    if (clean.length === 13) {
      if (isValidIsbn13(clean)) {
        return {
          isValid: true,
          isRequired: !isPre2011,
          normalized: clean,
          isIsbn10: false,
          isIsbn13: true,
        };
      }
      return {
        isValid: false,
        isRequired: !isPre2011,
        normalized: clean,
        isIsbn10: false,
        isIsbn13: true,
        error: 'Неверная контрольная сумма ISBN-13',
      };
    }

    return {
      isValid: false,
      isRequired: !isPre2011,
      normalized: clean,
      isIsbn10: false,
      isIsbn13: false,
      error: `ISBN должен содержать 10 или 13 знаков (передано: ${clean.length})`,
    };
  }

  /**
   * Валидация артикула товара
   */
  function validateArticle(article) {
    const raw = String(article || '').trim();
    if (!raw) {
      return { isValid: false, error: 'Артикул товара не может быть пустым' };
    }
    if (raw.length < 3 || raw.length > 50) {
      return { isValid: false, error: 'Длина артикула должна быть от 3 до 50 символов' };
    }
    if (!/^[A-Za-z0-9_\-\.]+$/.test(raw)) {
      return { isValid: false, error: 'Артикул может содержать только латиницу, цифры, дефис и подчеркивание' };
    }
    return { isValid: true, normalized: raw };
  }

  /**
   * Валидация цен книги для Ozon
   */
  function validatePrices(price, oldPrice) {
    const p = parseFloat(price);
    const op = parseFloat(oldPrice);
    const errors = [];
    const warnings = [];

    if (isNaN(p) || p <= 0) {
      errors.push('Цена продажи должна быть положительным числом больше 0 ₽');
    }
    if (!isNaN(op) && op > 0) {
      if (op <= p) {
        warnings.push('Старая цена (до скидки) должна быть выше текущей цены продажи');
      }
    }

    return {
      isValid: errors.length === 0,
      errors,
      warnings,
    };
  }

  /**
   * Комплексная валидация карточки книги перед публикацией в Ozon API.
   * Проверяет обязательные атрибуты категории Ozon "Печатные книги" (ID 17028757).
   * @param {Object} book - объект книги из BookStore или подготовленный payload
   * @returns {{ isValid: boolean, errors: string[], warnings: string[] }}
   */
  function validateBookForOzon(book) {
    const errors = [];
    const warnings = [];
    if (!book) {
      return { isValid: false, errors: ['Объект книги не передан'], warnings: [] };
    }

    const data = book.formData || book;

    // 1. Название (Attribute 4180)
    const title = String(data.title || '').trim();
    if (!title) {
      errors.push('Не указано название книги (обязательно для Ozon)');
    } else if (title.length > 500) {
      errors.push('Название книги превышает максимально допустимые 500 символов');
    }

    // 2. Автор (Attribute 105)
    const author = String(data.author || data.author_cover || '').trim();
    if (!author) {
      errors.push('Не указан автор книги (или укажите «не указан»)');
    }

    // 3. Год издания (Attribute 4081)
    const yearRaw = data.year;
    const year = parseInt(yearRaw, 10);
    if (!yearRaw || isNaN(year) || year < 1450 || year > 2099) {
      errors.push('Укажите корректный год издания книги (от 1450 до 2099)');
    }

    // 4. Цена (Price)
    const price = parseFloat(data.price);
    if (isNaN(price) || price <= 0) {
      errors.push('Укажите цену продажи (должна быть больше 0 ₽)');
    }

    // 5. Габариты и вес (Dimensions & Weight)
    const w = parseInt(data.width_package || data.width_mm || data.width, 10);
    const l = parseInt(data.length_package || data.length_mm || data.length, 10);
    const h = parseInt(data.height_package || data.height_mm || data.height, 10);
    const wt = parseInt(data.weight_package || data.weight_g || data.weight, 10);

    if (isNaN(w) || w <= 0 || isNaN(l) || l <= 0 || isNaN(h) || h <= 0) {
      errors.push('Не заполнены габариты упаковки (ширина, длина, высота в мм)');
    }
    if (isNaN(wt) || wt <= 0) {
      errors.push('Не указан вес книги с упаковкой в граммах');
    }

    // 6. Главное фото (Cover Front)
    const hasFrontCover = Boolean(
      (book.slots && book.slots.cover_front) ||
      (data.slots_photos && data.slots_photos.cover_front) ||
      data.primary_photo ||
      data.cover_front ||
      (Array.isArray(book.photos) && book.photos.length > 0)
    );
    if (!hasFrontCover) {
      errors.push('Отсутствует главное фото книги (обложка спереди)');
    }

    // 7. ISBN для книг после 2011 года
    const mode = resolveTemplateMode(year);
    if (mode === 'post2011') {
      const isbnRes = validateIsbn(data.isbn, year);
      if (!isbnRes.isValid) {
        errors.push(`Для книг после 2011 года требуется валидный ISBN: ${isbnRes.error || 'не указан'}`);
      }
    }

    // 8. Артикул
    const article = String(data.article || '').trim();
    if (!article) {
      errors.push('Не указан артикул товара (DP-B-XXXXX)');
    }

    return {
      isValid: errors.length === 0,
      errors,
      warnings,
    };
  }

  const BookValidators = {
    resolveTemplateMode,
    isValidIsbn10,
    isValidIsbn13,
    convertIsbn10To13,
    validateIsbn,
    validateArticle,
    validatePrices,
    validateBookForOzon,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = BookValidators;
  }
  if (typeof global !== 'undefined') {
    global.BookValidators = BookValidators;
  }
})(typeof window !== 'undefined' ? window : global);
