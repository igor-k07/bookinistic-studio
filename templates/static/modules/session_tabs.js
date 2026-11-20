/**
 * session_tabs.js: Управление сессиями книг, вкладками, переключением, автосохранением черновиков и артикулами.
 */

(function (window) {
  'use strict';

  const FORM_FIELD_IDS = [
    'article', 'article_number', 'barcode', 'isbn', 'title', 'original_title', 'series', 'author_cover', 'author',
    'illustrator', 'translator', 'publisher', 'brand', 'year', 'country', 'pages', 'cover_type',
    'paper_type', 'genre', 'age_limit', 'target_audience', 'condition',
    'annotation', 'hashtags', 'price', 'old_price', 'dimensions', 'weight',
    'width', 'length', 'height',
    'width_package', 'length_package', 'height_package', 'weight_package'
  ];
  window.FORM_FIELD_IDS = FORM_FIELD_IDS;

  // -------------------------------------------------------------
  // АВТОСОХРАНЕНИЕ И ВОССТАНОВЛЕНИЕ ПОДГОТОВЛЕННЫХ КНИГ (DRAFT PERSISTENCE)
  // -------------------------------------------------------------
  function scheduleAutoSave() {
    saveCurrentFormToActiveBook();
    updateAutoSaveStatus('saving');
    clearTimeout(window.autoSaveTimer);
    window.autoSaveTimer = setTimeout(performAutoSave, 500);
  }

  async function performAutoSave() {
    saveCurrentFormToActiveBook();
    try {
      // Компактный photoPool без раздутой истории undo и дубликатов data
      const cleanPool = (window.photoPool || []).map(p => {
        const item = {
          id: p.id,
          name: p.name || 'photo.jpg',
          mime: p.mime || 'image/jpeg',
          preview: p.preview || p.cameraOriginal,
          cameraOriginal: p.cameraOriginal || p.rawOriginal || p.preview,
          rawOriginal: p.cameraOriginal || p.rawOriginal || p.preview,
          croppedBase: p.croppedBase || null,
          aiWhiteOriginal: p.aiWhiteOriginal || null,
          isCropped: Boolean(p.isCropped),
          isAiProcessed: Boolean(p.isAiProcessed),
          whiten: p.whiten || 0,
          brightness: p.brightness || 0,
          contrast: p.contrast || 0,
          saturation: p.saturation || 0,
          rotation: p.rotation || 0,
          assignedBookId: p.assignedBookId || null,
          assignedSlot: p.assignedSlot || null
        };
        if (p.aiCropRelative) item.aiCropRelative = p.aiCropRelative;
        if (p.cropRelative) item.cropRelative = p.cropRelative;
        if (p.cropBoxOnOriginal) item.cropBoxOnOriginal = p.cropBoxOnOriginal;
        return item;
      });

      // Де-дуплицированные слоты книг (только id)
      const cleanBooks = (window.booksSession || []).map(b => {
        const slots = b.slots || {};
        return {
          ...b,
          slots: {
            cover_front: (slots.cover_front && slots.cover_front.id) ? { id: slots.cover_front.id } : null,
            cover_back: Array.isArray(slots.cover_back)
              ? slots.cover_back.filter(p => p && p.id).map(p => ({ id: p.id }))
              : ((slots.cover_back && slots.cover_back.id) ? [{ id: slots.cover_back.id }] : []),
            info_pages: (slots.info_pages || []).filter(p => p && p.id).map(p => ({ id: p.id })),
            illustrations: (slots.illustrations || []).filter(p => p && p.id).map(p => ({ id: p.id })),
            mantra_defects: (slots.mantra_defects || []).filter(p => p && p.id).map(p => ({ id: p.id }))
          }
        };
      });

      const payload = {
        has_draft: true,
        activeBookId: window.activeBookId,
        booksSession: cleanBooks,
        photoPool: cleanPool,
        timestamp: Date.now()
      };

      const resData = window.ApiClient
        ? await window.ApiClient.saveSessionDraft(payload)
        : await fetch('/api/save_draft', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          }).then(r => r.json());

      if (resData.success) {
        if (resData.updated_urls) {
          // Освобождаем память в браузере, заменяя base64 на легкие локальные URL
          Object.keys(resData.updated_urls).forEach(pid => {
            const p = window.findPhotoById ? window.findPhotoById(pid) : null;
            if (p) {
              const urls = resData.updated_urls[pid];
              if (urls.preview) p.preview = urls.preview;
              if (urls.cameraOriginal) p.cameraOriginal = urls.cameraOriginal;
              if (urls.rawOriginal) p.rawOriginal = urls.rawOriginal;
              if (urls.croppedBase) p.croppedBase = urls.croppedBase;
              if (urls.aiWhiteOriginal) p.aiWhiteOriginal = urls.aiWhiteOriginal;
              delete p.data;
            }
          });
        }
        updateAutoSaveStatus('saved');
      } else {
        updateAutoSaveStatus('error');
      }
    } catch (err) {
      console.warn('Auto-save error:', err);
      updateAutoSaveStatus('error');
    }
  }

  function updateAutoSaveStatus(state) {
    const el = document.getElementById('sessionSaveStatus');
    if (!el) return;
    if (state === 'saving') {
      el.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"></span><span class="text-amber-400">Сохранение...</span>';
    } else if (state === 'saved') {
      el.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span><span class="text-slate-400">Черновик сохранен</span>';
    } else if (state === 'restored') {
      el.innerHTML = '<span class="w-1.5 h-1.5 rounded-full bg-sky-400"></span><span class="text-sky-300 font-semibold">Черновик восстановлен</span>';
      setTimeout(() => updateAutoSaveStatus('saved'), 3500);
    }
  }

  async function restoreSessionDraft() {
    try {
      const draft = window.ApiClient
        ? await window.ApiClient.getSessionDraft()
        : await fetch('/api/get_draft').then(r => r.json());

      if (draft && draft.booksSession && draft.booksSession.length > 0) {
        window.booksSession = draft.booksSession;
        window.photoPool = draft.photoPool || [];
        window.activeBookId = draft.activeBookId || window.booksSession[0].id;

        // Санитизация аннотаций: убираем предупреждения из черновика для книг без дефектов
        window.booksSession.forEach(b => {
          const hasDefects = Boolean(b.slots && b.slots.mantra_defects && b.slots.mantra_defects.length > 0);
          if (!hasDefects && b.formData && b.formData.annotation && typeof window.cleanAnnotationText === 'function') {
            b.formData.annotation = window.cleanAnnotationText(b.formData.annotation);
          }
        });

        relinkSessionPhotos();
        renderBooksTabs();
        restoreFormFromActiveBook();
        if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
        if (typeof window.renderPool === 'function') window.renderPool();
        if (typeof window.autoCalcDimensions === 'function') window.autoCalcDimensions();
        if (typeof window.autoDetectCountry === 'function') window.autoDetectCountry();
        updateAutoSaveStatus('restored');
        return true;
      }
    } catch (e) {
      console.warn('Draft restore failed:', e);
    }
    return false;
  }

  function relinkSessionPhotos() {
    const map = new Map();
    (window.photoPool || []).forEach(p => {
      if (!p.cameraOriginal) p.cameraOriginal = p.rawOriginal || p.preview;
      if (!p.rawOriginal) p.rawOriginal = p.cameraOriginal;
      if (!p.preview) p.preview = p.cameraOriginal || p.rawOriginal || (p.data ? ('data:' + (p.mime || 'image/jpeg') + ';base64,' + p.data) : '');
      if (p.isCropped === undefined) p.isCropped = Boolean(p.croppedBase);
      if (p.croppedBase === undefined) p.croppedBase = null;
      if (typeof window.isPhotoProcessed === 'function') {
        p.isProcessed = window.isPhotoProcessed(p);
      }
      map.set(p.id, p);
    });

    (window.booksSession || []).forEach(b => {
      if (!b.slots) b.slots = {};
      if (b.slots.cover_front && b.slots.cover_front.id) {
        if (map.has(b.slots.cover_front.id)) {
          b.slots.cover_front = map.get(b.slots.cover_front.id);
        } else if (b.slots.cover_front.preview) {
          window.photoPool.push(b.slots.cover_front);
          map.set(b.slots.cover_front.id, b.slots.cover_front);
        } else {
          b.slots.cover_front = null;
        }
      }
      ['cover_back', 'info_pages', 'illustrations', 'mantra_defects'].forEach(s => {
        let list = b.slots[s];
        if (!Array.isArray(list)) {
          list = (list && list.id) ? [list] : [];
        }
        b.slots[s] = list.map(p => {
          if (p && p.id && map.has(p.id)) return map.get(p.id);
          if (p && p.preview) {
            window.photoPool.push(p);
            map.set(p.id, p);
            return p;
          }
          return null;
        }).filter(Boolean);
      });
    });
  }

  async function resetCurrentBook() {
    const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
    if (!book) return;

    const art = (book.formData && book.formData.article) || book.article || `Книга #${book.id}`;
    if (!confirm(`Сбросить все заполненные блоки и слоты для ${art}?\n\nВсе прикрепленные фотографии этой книги вернутся в свободный пул.`)) {
      return;
    }

    // 1. Освобождаем все фото текущей книги обратно в свободный пул
    if (book.slots.cover_front) {
      book.slots.cover_front.assignedBookId = null;
      book.slots.cover_front.assignedSlot = null;
      book.slots.cover_front = null;
    }
    ['cover_back', 'info_pages', 'illustrations', 'mantra_defects'].forEach(s => {
      const list = Array.isArray(book.slots[s]) ? book.slots[s] : (book.slots[s] ? [book.slots[s]] : []);
      list.forEach(p => {
        p.assignedBookId = null;
        p.assignedSlot = null;
      });
      book.slots[s] = [];
    });

    // 2. Очищаем все поля карточки товара, сохраняя артикул
    if (typeof window.clearForm === 'function') {
      await window.clearForm(book.article);
    }
    if (document.getElementById('autoPackageAdder')) {
      document.getElementById('autoPackageAdder').checked = true;
    }
    book.formData = {
      article: book.article,
      article_number: book.article.replace(/\D/g, '').slice(-5),
      barcode: document.getElementById('barcode')?.value || '',
      template_mode: window.currentTemplateMode || 'pre2011',
      auto_package_adder: true
    };
    if (typeof window.autoCalcDimensions === 'function') window.autoCalcDimensions();

    // 3. Обновляем интерфейс: освобожденные фото сразу вернутся в пул
    renderBooksTabs();
    if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
    if (typeof window.renderPool === 'function') window.renderPool();
    scheduleAutoSave();
  }

  async function fetchDbNextArticle() {
    try {
      const res = window.ApiClient
        ? await window.ApiClient.getNextArticle()
        : await fetch('/api/get_next_article').then(r => r.json());
      if (res && res.success && res.article) {
        return res.article;
      }
    } catch (e) {
      console.warn('Failed to fetch /api/get_next_article:', e);
    }
    return null;
  }

  function formatArticleInput(val) {
    const clean = String(val || '').trim();
    const m = clean.match(/DP-B-(\d+)/i) || clean.match(/(\d+)/);
    const num = m ? parseInt(m[1], 10) : 1;
    const padded = String(num).padStart(5, '0');
    return `DP-B-${padded}`;
  }

  async function openNewSessionModal() {
    const modal = document.getElementById('newSessionModal');
    if (!modal) return;

    // Сначала показываем модалку, чтобы интерфейс мгновенно реагировал
    modal.classList.remove('hidden');

    const input = document.getElementById('newSessionStartArticleInput');
    if (input) {
      // Подставляем временное значение пока ждем запрос
      if (!input.value) input.value = 'DP-B-02884';
      input.focus();
      input.select();
    }

    // Получаем актуальный следующий свободный артикул из базы
    let nextArt = await fetchDbNextArticle();
    if (!nextArt) {
      nextArt = await calculateNextArticle(0);
    }

    if (input && nextArt) {
      input.value = nextArt;
      input.focus();
      input.select();
    }
  }

  function closeNewSessionModal() {
    const modal = document.getElementById('newSessionModal');
    if (modal) modal.classList.add('hidden');
  }

  async function refreshNewSessionNextArticle() {
    const spinner = document.getElementById('newSessionRefreshSpinner');
    if (spinner) spinner.classList.add('animate-spin');
    try {
      let nextArt = await fetchDbNextArticle();
      if (!nextArt) nextArt = await calculateNextArticle(0);
      const input = document.getElementById('newSessionStartArticleInput');
      if (input && nextArt) {
        input.value = nextArt;
        input.select();
      }
    } finally {
      if (spinner) {
        setTimeout(() => spinner.classList.remove('animate-spin'), 350);
      }
    }
  }

  async function executeStartNewSession() {
    const input = document.getElementById('newSessionStartArticleInput');
    const rawVal = input ? input.value.trim() : '';
    const formattedArt = formatArticleInput(rawVal);
    const numPart = formattedArt.replace(/\D/g, '').slice(-5);
    const newBarcode = window.BookCalculators
      ? window.BookCalculators.generateEan13FromArticle(formattedArt)
      : (window.generateEan13FromArticle ? window.generateEan13FromArticle(formattedArt) : '2978470000012');

    // 1. Закрываем модальное окно
    closeNewSessionModal();

    // 2. Если открыта Photo Studio — закрываем её без сохранения
    if (typeof window.closePhotoStudio === 'function') {
      try { window.closePhotoStudio(true); } catch (e) {}
    }

    // 3. Очищаем черновик и временные фото на сервере
    try {
      if (window.ApiClient && typeof window.ApiClient.clearSessionDraft === 'function') {
        await window.ApiClient.clearSessionDraft();
      } else {
        await fetch('/api/clear_session_draft', { method: 'POST' });
      }
    } catch (err) {
      console.warn('Failed to clear session draft on server:', err);
    }

    // 4. Очищаем локальный пул фотографий
    window.photoPool = [];
    window.selectedPoolPhotoId = null;

    // 5. Инициализируем ровно одну чистую книгу с выбранным артикулом
    window.booksSession = [{
      id: 1,
      article: formattedArt,
      title: 'Книга #1',
      slots: {
        cover_front: null,
        cover_back: [],
        info_pages: [],
        illustrations: [],
        mantra_defects: []
      },
      formData: {
        article: formattedArt,
        article_number: numPart,
        barcode: newBarcode,
        auto_package_adder: true,
        template_mode: window.currentTemplateMode || 'pre2011'
      }
    }];
    window.activeBookId = 1;

    // 6. Очищаем форму книги и выставляем стартовые реквизиты
    if (typeof window.clearForm === 'function') {
      await window.clearForm(formattedArt);
    }
    syncArticleInputs(formattedArt);

    const barcodeEl = document.getElementById('barcode');
    if (barcodeEl) barcodeEl.value = newBarcode;

    const pkgCheck = document.getElementById('autoPackageAdder');
    if (pkgCheck) pkgCheck.checked = true;

    // 7. Обновляем стартовый артикул в панели авто-конвейера
    const batchStartInput = document.getElementById('batchStartArticle');
    if (batchStartInput) batchStartInput.value = formattedArt;

    // 8. Сбрасываем ID мобильных событий, чтобы слушать только новые фото
    if (typeof window.lastMobileEventId !== 'undefined') {
      window.lastMobileEventId = 0;
    }

    // 9. Перерисовываем интерфейс (пул, слоты, вкладки)
    renderBooksTabs();
    if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
    if (typeof window.renderPool === 'function') window.renderPool();
    if (typeof window.autoCalcDimensions === 'function') window.autoCalcDimensions();
    if (typeof window.autoDetectCountry === 'function') window.autoDetectCountry();

    // 10. Сохраняем чистый начальный черновик
    scheduleAutoSave();

    // 11. Оповещаем пользователя
    if (typeof window.showToast === 'function') {
      window.showToast(`🚀 Новая сессия начата! Пул очищен, стартовый артикул: ${formattedArt}`);
    }
  }

  async function resetWholeSession() {
    return openNewSessionModal();
  }

  async function initBatchArticleInput() {
    const el = document.getElementById('batchStartArticle');
    if (el && !el.value) {
      const nextArt = await calculateNextArticle(0);
      el.value = nextArt;
    }
  }

  async function calculateNextArticle(offset = 0) {
    let maxSessionNum = 0;
    if (typeof window.booksSession !== 'undefined' && Array.isArray(window.booksSession)) {
      window.booksSession.forEach(b => {
        const art = (b.formData && (b.formData.article || b.formData.article_number)) || b.article || '';
        const digits = String(art).replace(/\D/g, '');
        if (digits) {
          const val = parseInt(digits, 10);
          if (val > maxSessionNum) maxSessionNum = val;
        }
      });
    }

    if (maxSessionNum > 0) {
      const nextNum = maxSessionNum + 1 + offset;
      return `DP-B-${String(nextNum).padStart(5, '0')}`;
    }

    // Проверяем глобальный артикул из БД и архива books_vault
    const dbArt = await fetchDbNextArticle();
    if (dbArt) {
      const digits = String(dbArt).replace(/\D/g, '');
      if (digits) {
        const val = parseInt(digits, 10);
        return `DP-B-${String(val + offset).padStart(5, '0')}`;
      }
    }

    try {
      const res = await fetch('/api/get_books');
      const data = await res.json();
      let maxExcelNum = 0;
      const allBooks = [];
      if (data.books && Array.isArray(data.books)) allBooks.push(...data.books);
      allBooks.forEach(b => {
        const digits = String(b.article || '').replace(/\D/g, '');
        if (digits) {
          const val = parseInt(digits, 10);
          if (val > maxExcelNum) maxExcelNum = val;
        }
      });
      const baseCount = (typeof data.total === 'number') ? data.total : allBooks.length;
      const nextNum = Math.max(maxExcelNum, baseCount) + 1 + offset;
      return `DP-B-${String(nextNum).padStart(5, '0')}`;
    } catch (e) {
      return `DP-B-${String(1 + offset).padStart(5, '0')}`;
    }
  }

  async function addNewBook() {
    saveCurrentFormToActiveBook();
    const books = window.booksSession || [];
    const nextId = books.length > 0 ? Math.max(...books.map(b => b.id)) + 1 : 1;
    const nextArt = await calculateNextArticle(books.length);
    const nextBarcode = window.BookCalculators
      ? window.BookCalculators.generateEan13FromArticle(nextArt)
      : (window.generateEan13FromArticle ? window.generateEan13FromArticle(nextArt) : '2978470000012');
    const numPart = nextArt.replace(/\D/g, '').slice(-5);
    const newBook = {
      id: nextId,
      article: nextArt,
      title: `Книга #${nextId}`,
      slots: {
        cover_front: null,
        cover_back: [],
        info_pages: [],
        illustrations: [],
        mantra_defects: []
      },
      formData: {
        article: nextArt,
        article_number: numPart,
        barcode: nextBarcode,
        auto_package_adder: true
      }
    };
    books.push(newBook);
    window.activeBookId = nextId;
    renderBooksTabs();
    if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
    if (typeof window.clearForm === 'function') window.clearForm(nextArt);
    scheduleAutoSave();
  }

  function deleteBookSession(id, e) {
    if (e) e.stopPropagation();
    if (!window.booksSession || window.booksSession.length <= 1) {
      alert('В сессии должна оставаться как минимум одна книга!');
      return;
    }
    if (!confirm('Удалить эту карточку книги из текущей сессии? Фото вернутся в общий пул.')) return;

    (window.photoPool || []).forEach(p => {
      if (p.assignedBookId === id) {
        p.assignedBookId = null;
        p.assignedSlot = null;
      }
    });

    window.booksSession = window.booksSession.filter(b => b.id !== id);
    if (window.activeBookId === id) {
      window.activeBookId = window.booksSession[0].id;
    }
    if (typeof window.renderPool === 'function') window.renderPool();
    renderBooksTabs();
    restoreFormFromActiveBook();
    if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
    scheduleAutoSave();
  }

  function syncArticleInputs(fullArt) {
    const art = String(fullArt || '').trim();
    const m = art.match(/DP-B-(\d+)/i) || art.match(/(\d+)/);
    let numStr = m ? m[1] : '1';
    const padded = numStr.padStart(5, '0');
    const full = `DP-B-${padded}`;
    const artEl = document.getElementById('article');
    if (artEl) artEl.value = full;
    const numEl = document.getElementById('article_number');
    if (numEl) numEl.value = padded;
    return full;
  }

  function onArticleNumberInput(val) {
    const digits = String(val || '').replace(/\D/g, '').slice(0, 5);
    const numEl = document.getElementById('article_number');
    if (numEl && numEl.value !== digits) {
      numEl.value = digits;
    }
    const padded = digits ? digits.padStart(5, '0') : '00001';
    const fullArt = `DP-B-${padded}`;
    const artEl = document.getElementById('article');
    if (artEl) artEl.value = fullArt;

    const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
    if (book) {
      book.article = fullArt;
      if (!book.formData) book.formData = {};
      book.formData.article = fullArt;
      book.formData.article_number = digits;

      const bcEl = document.getElementById('barcode');
      const curBc = bcEl ? bcEl.value.trim() : '';
      if (!curBc || curBc === 'генерирует озон' || curBc.startsWith('29')) {
        const newBc = window.BookCalculators
          ? window.BookCalculators.generateEan13FromArticle(fullArt)
          : (window.generateEan13FromArticle ? window.generateEan13FromArticle(fullArt) : '2978470000012');
        if (bcEl) bcEl.value = newBc;
        book.formData.barcode = newBc;
      }
    }
    renderBooksTabs();
    scheduleAutoSave();
  }

  function onArticleNumberBlur() {
    const numEl = document.getElementById('article_number');
    if (numEl) {
      const digits = numEl.value.replace(/\D/g, '');
      if (digits) {
        const padded = digits.padStart(5, '0');
        numEl.value = padded;
        const fullArt = `DP-B-${padded}`;
        const artEl = document.getElementById('article');
        if (artEl) artEl.value = fullArt;
        const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
        if (book) {
          book.article = fullArt;
          if (!book.formData) book.formData = {};
          book.formData.article = fullArt;
          book.formData.article_number = padded;
        }
        renderBooksTabs();
        scheduleAutoSave();
      }
    }
  }

  function onArticleInput(val) {
    const fullArt = syncArticleInputs(val);
    const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
    if (!book) return;
    book.article = fullArt;
    if (!book.formData) book.formData = {};
    book.formData.article = fullArt;
    book.formData.article_number = fullArt.replace(/\D/g, '').slice(-5);

    const bcEl = document.getElementById('barcode');
    const curBc = bcEl ? bcEl.value.trim() : '';
    if (!curBc || curBc === 'генерирует озон' || curBc.startsWith('29')) {
      const newBc = window.BookCalculators
        ? window.BookCalculators.generateEan13FromArticle(fullArt)
        : (window.generateEan13FromArticle ? window.generateEan13FromArticle(fullArt) : '2978470000012');
      if (bcEl) bcEl.value = newBc;
      book.formData.barcode = newBc;
    }

    renderBooksTabs();
    scheduleAutoSave();
  }

  function onBarcodeInput(val) {
    const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
    if (!book) return;
    if (!book.formData) book.formData = {};
    book.formData.barcode = val.trim();
    scheduleAutoSave();
  }

  function onTitleInput(val) {
    const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
    if (!book) return;
    if (!book.formData) book.formData = {};
    book.formData.title = val;
    renderBooksTabs();
    scheduleAutoSave();
  }

  function saveCurrentFormToActiveBook() {
    const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
    if (!book) return;
    if (!book.formData) book.formData = {};
    FORM_FIELD_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (el) book.formData[id] = el.value;
    });
    if (document.getElementById('autoPackageAdder')) {
      book.formData.auto_package_adder = document.getElementById('autoPackageAdder').checked;
    }
    book.formData.template_mode = window.currentTemplateMode;
    if (book.formData.article) book.article = book.formData.article;
  }

  function restoreFormFromActiveBook() {
    const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
    if (!book) return;
    if (!book.formData) book.formData = {};

    FORM_FIELD_IDS.forEach(id => {
      const el = document.getElementById(id);
      if (el) {
        el.value = (book.formData[id] !== undefined && book.formData[id] !== null) ? String(book.formData[id]) : '';
      }
    });
    if (document.getElementById('autoPackageAdder')) {
      document.getElementById('autoPackageAdder').checked = (book.formData.auto_package_adder !== false);
    }
    // Нормализация жанра: исключаем 'Детская литература' из черновиков
    if (book.formData['genre'] === 'Детская литература' || (book.formData['genre'] && String(book.formData['genre']).toLowerCase().includes('детск'))) {
      book.formData['genre'] = (typeof window.resolveOzonGenre === 'function')
        ? window.resolveOzonGenre(book.formData['genre'], book.formData['title'], book.formData['annotation'])
        : 'Проза';
      const gEl = document.getElementById('genre');
      if (gEl) gEl.value = book.formData['genre'];
    }
    // Распаковка габаритов для старых черновиков если width/length отсутствуют
    const wEl = document.getElementById('width');
    const lEl = document.getElementById('length');
    const hEl = document.getElementById('height');
    if ((!wEl?.value || !lEl?.value) && book.formData.dimensions) {
      const parts = String(book.formData.dimensions).split(/[хxXХ*×/]/).map(p => parseInt(p.trim())).filter(n => !isNaN(n));
      if (parts.length >= 3) {
        if (wEl && !wEl.value) wEl.value = parts[0];
        if (lEl && !lEl.value) lEl.value = parts[1];
        if (hEl && !hEl.value) hEl.value = parts[2];
      }
    }
    const art = (book.formData && book.formData.article) || book.article || 'DP-B-00001';
    syncArticleInputs(art);
    const defectCount = (book.slots && book.slots.mantra_defects) ? book.slots.mantra_defects.length : 0;
    if (typeof window.setCondition === 'function') {
      if (defectCount === 0) {
        window.setCondition('Очень хорошая', false);
      } else if (book.formData && book.formData.condition === 'Удовлетворительная') {
        window.setCondition('Удовлетворительная', false);
      } else {
        window.setCondition('Хорошая', false);
      }
    }
    const mode = book.formData.template_mode || (parseInt(book.formData.year) > 2011 ? 'post2011' : 'pre2011');
    if (typeof window.setTemplateMode === 'function') {
      window.setTemplateMode(mode, false);
    }
    if (typeof window.updateDimensionsPreviewBadge === 'function') {
      window.updateDimensionsPreviewBadge();
    }
    if (typeof window.syncAnnotationWarningWithDefectsSlot === 'function') {
      window.syncAnnotationWarningWithDefectsSlot();
    }
  }

  function switchBook(id) {
    if (window.activeBookId === id) return;
    saveCurrentFormToActiveBook();
    window.activeBookId = id;
    renderBooksTabs();
    restoreFormFromActiveBook();
    if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
    scheduleAutoSave();
  }

  function renderBooksTabs() {
    const container = document.getElementById('booksTabsContainer');
    if (!container) return;
    container.innerHTML = (window.booksSession || []).map(b => {
      const isActive = b.id === window.activeBookId;
      const art = (b.formData && b.formData.article) || b.article || `Книга #${b.id}`;
      const titleSnippet = (b.formData && b.formData.title) ? ` • ${b.formData.title.substring(0, 16)}` : '';
      const count = [
        b.slots.cover_front ? 1 : 0,
        Array.isArray(b.slots.cover_back) ? b.slots.cover_back.length : (b.slots.cover_back ? 1 : 0),
        (b.slots.info_pages || []).length,
        (b.slots.illustrations || []).length,
        (b.slots.mantra_defects || []).length
      ].reduce((a, b) => a + b, 0);

      const statusIcon = b.isAiRecognizing ? '⏳' : (b.isAiRecognized ? '✨' : (b.isSavedToExcel ? '✅' : '📖'));
      return `
        <div class="inline-flex items-center rounded-xl overflow-hidden border transition ${isActive ? 'border-amber-500 bg-amber-500 text-slate-950 font-bold shadow-md shadow-amber-500/20' : 'border-slate-700 bg-slate-800 hover:bg-slate-750 text-slate-300'}">
          <button type="button" onclick="switchBook(${b.id})" class="px-3 py-1.5 text-xs font-semibold flex items-center gap-2 text-left" title="${b.isAiRecognizing ? 'Книга сейчас анализируется нейросетью Gemini...' : (b.isAiRecognized ? 'Книга успешно распознана нейросетью!' : '')}">
            <span>${statusIcon} <span class="font-mono tracking-tight font-bold">${art}</span><span class="opacity-80">${titleSnippet}</span></span>
            <span class="px-1.5 py-0.2 rounded-full text-[10px] ${isActive ? 'bg-slate-950 text-amber-300' : 'bg-slate-900 text-slate-400'} font-mono">${count} фото</span>
          </button>
          ${(window.booksSession || []).length > 1 ? `
            <button type="button" onclick="deleteBookSession(${b.id}, event)" class="px-2 py-1.5 text-xs ${isActive ? 'text-slate-950 hover:bg-amber-400 hover:text-rose-950' : 'text-slate-400 hover:bg-slate-700 hover:text-rose-400'} transition font-bold" title="Удалить карточку этой книги">✕</button>
          ` : ''}
        </div>
      `;
    }).join('');
    const cur = typeof getActiveBook === 'function' ? getActiveBook() : null;
    const titleEl = document.getElementById('activeBookTitle');
    if (cur && titleEl) {
      const curArt = (cur.formData && cur.formData.article) || cur.article || `Книга #${cur.id}`;
      titleEl.textContent = `📚 [${curArt}]: Слоты категорий`;
    }
  }

  // Экспорт на window
  window.scheduleAutoSave = scheduleAutoSave;
  window.performAutoSave = performAutoSave;
  window.updateAutoSaveStatus = updateAutoSaveStatus;
  window.restoreSessionDraft = restoreSessionDraft;
  window.relinkSessionPhotos = relinkSessionPhotos;
  window.resetCurrentBook = resetCurrentBook;
  window.resetWholeSession = resetWholeSession;
  window.fetchDbNextArticle = fetchDbNextArticle;
  window.formatArticleInput = formatArticleInput;
  window.openNewSessionModal = openNewSessionModal;
  window.closeNewSessionModal = closeNewSessionModal;
  window.refreshNewSessionNextArticle = refreshNewSessionNextArticle;
  window.executeStartNewSession = executeStartNewSession;
  window.initBatchArticleInput = initBatchArticleInput;
  window.calculateNextArticle = calculateNextArticle;
  window.addNewBook = addNewBook;
  window.deleteBookSession = deleteBookSession;
  window.syncArticleInputs = syncArticleInputs;
  window.onArticleNumberInput = onArticleNumberInput;
  window.onArticleNumberBlur = onArticleNumberBlur;
  window.onArticleInput = onArticleInput;
  window.onBarcodeInput = onBarcodeInput;
  window.onTitleInput = onTitleInput;
  window.saveCurrentFormToActiveBook = saveCurrentFormToActiveBook;
  window.restoreFormFromActiveBook = restoreFormFromActiveBook;
  window.switchBook = switchBook;
  window.renderBooksTabs = renderBooksTabs;

})(window);

