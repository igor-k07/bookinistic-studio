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
      // 1. Гарантируем, что любые фото из слотов всех книг зарегистрированы в photoPool со всеми URL и привязкой к слотам
      if (window.photoPool && Array.isArray(window.photoPool)) {
        (window.booksSession || []).forEach(b => {
          if (!b || !b.slots) return;
          const slotMap = [
            ['cover_front', b.slots.cover_front ? [b.slots.cover_front] : []],
            ['cover_back', Array.isArray(b.slots.cover_back) ? b.slots.cover_back : (b.slots.cover_back ? [b.slots.cover_back] : [])],
            ['info_pages', b.slots.info_pages || []],
            ['illustrations', b.slots.illustrations || []],
            ['mantra_defects', b.slots.mantra_defects || []]
          ];

          slotMap.forEach(([sName, items]) => {
            items.forEach(p => {
              if (p && p.id && (p.preview || p.cameraOriginal || p.url || p.data)) {
                p.assignedBookId = b.id;
                p.assignedSlot = sName;
                const exIdx = window.photoPool.findIndex(x => x.id === p.id);
                if (exIdx >= 0) {
                  const ex = window.photoPool[exIdx];
                  ex.assignedBookId = b.id;
                  ex.assignedSlot = sName;
                  if (!ex.preview && p.preview) ex.preview = p.preview;
                  if (!ex.cameraOriginal && (p.cameraOriginal || p.url)) ex.cameraOriginal = p.cameraOriginal || p.url;
                  if (!ex.rawOriginal && (p.rawOriginal || p.cameraOriginal || p.url)) ex.rawOriginal = p.rawOriginal || p.cameraOriginal || p.url;
                  if (!ex.url && p.url) ex.url = p.url;
                  if (!ex.name && p.name) ex.name = p.name;
                  if (p.s3_url && !ex.s3_url) ex.s3_url = p.s3_url;
                }
                // Фото слотов книги хранятся в b.slots, не дублируем их в общий photoPool
              }
            });
          });
        });
      }

      // Компактный photoPool без раздутой истории undo и дубликатов data
      const cleanPool = (window.photoPool || []).map(p => {
        const item = {
          id: p.id,
          name: p.name || 'photo.jpg',
          mime: p.mime || 'image/jpeg',
          preview: p.preview || p.cameraOriginal || p.url,
          cameraOriginal: p.cameraOriginal || p.rawOriginal || p.preview || p.url,
          rawOriginal: p.rawOriginal || p.cameraOriginal || p.preview || p.url,
          croppedBase: p.croppedBase || null,
          aiWhiteOriginal: p.aiWhiteOriginal || null,
          url: p.url || p.preview || null,
          isCropped: Boolean(p.isCropped),
          isAiProcessed: Boolean(p.isAiProcessed),
          isFromVault: Boolean(p.isFromVault),
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

      // Дублируем сохранение в localStorage на случай мгновенного закрытия/перезагрузки страницы
      try {
        localStorage.setItem('bookinistic_session_draft', JSON.stringify(payload));
      } catch (locErr) {}

      const resData = window.ApiClient
        ? await window.ApiClient.saveSessionDraft(payload)
        : await fetch('/api/save_session_draft', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          }).then(r => r.json());

      if (resData.success) {
        if (resData.updated_urls) {
          // Освобождаем память в браузере, заменяя base64 на легкие локальные URL
          let hasUrlUpdates = false;
          Object.keys(resData.updated_urls).forEach(pid => {
            const p = window.findPhotoById ? window.findPhotoById(pid) : null;
            if (p) {
              const urls = resData.updated_urls[pid];
              if (urls.preview && p.preview !== urls.preview) {
                p.preview = urls.preview;
                hasUrlUpdates = true;
              }
              if (urls.cameraOriginal) p.cameraOriginal = urls.cameraOriginal;
              if (urls.rawOriginal) p.rawOriginal = urls.rawOriginal;
              if (urls.croppedBase && p.croppedBase !== urls.croppedBase) {
                p.croppedBase = urls.croppedBase;
                hasUrlUpdates = true;
              }
              if (urls.aiWhiteOriginal) p.aiWhiteOriginal = urls.aiWhiteOriginal;
              delete p.data;
            }
          });
          if (hasUrlUpdates) {
            if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
            if (typeof window.renderPool === 'function') window.renderPool();
          }
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
      let draft = window.ApiClient
        ? await window.ApiClient.getSessionDraft()
        : await fetch('/api/get_session_draft').then(r => r.json());

      if (!draft || !draft.booksSession || draft.booksSession.length === 0) {
        try {
          const localStr = localStorage.getItem('bookinistic_session_draft');
          if (localStr) {
            draft = JSON.parse(localStr);
          }
        } catch (lErr) {}
      }

      if (draft && draft.booksSession && draft.booksSession.length > 0) {
        if (window.BookStore) {
          window.BookStore.init(draft.booksSession, draft.activeBookId || draft.booksSession[0].id);
        } else {
          window.booksSession = draft.booksSession;
          window.activeBookId = draft.activeBookId || window.booksSession[0].id;
        }
        window.photoPool = draft.photoPool || [];

        // Санитизация аннотаций: убираем предупреждения только если нет дефектов И состояние не ухудшено вручную
        window.booksSession.forEach(b => {
          const hasDefects = Boolean(b.slots && b.slots.mantra_defects && b.slots.mantra_defects.length > 0);
          const cond = b.formData && b.formData.condition;
          const isManual = b.formData && b.formData.is_manual_condition;
          const isDowngraded = isManual && (cond === 'Хорошая' || cond === 'Удовлетворительная');
          if (!hasDefects && !isDowngraded && b.formData && b.formData.annotation && typeof window.cleanAnnotationText === 'function') {
            b.formData.annotation = window.cleanAnnotationText(b.formData.annotation);
          }
        });

        relinkSessionPhotos();
        renderBooksTabs();
        restoreFormFromActiveBook();
        if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
        if (typeof window.renderPool === 'function') window.renderPool();
        if (typeof window.updateDimensionsPreviewBadge === 'function') window.updateDimensionsPreviewBadge();
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
      if (!p.preview && (p.url || p.cameraOriginal)) p.preview = p.url || p.cameraOriginal;
      if (!p.cameraOriginal) p.cameraOriginal = p.rawOriginal || p.preview || p.url;
      if (!p.rawOriginal) p.rawOriginal = p.cameraOriginal || p.preview || p.url;
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
        b.slots.cover_front.assignedBookId = b.id;
        b.slots.cover_front.assignedSlot = 'cover_front';
        if (map.has(b.slots.cover_front.id)) {
          const item = map.get(b.slots.cover_front.id);
          item.assignedBookId = b.id;
          item.assignedSlot = 'cover_front';
          if (!item.preview && (b.formData && b.formData.main_photo_url)) {
            item.preview = b.formData.main_photo_url;
            item.url = b.formData.main_photo_url;
            item.cameraOriginal = b.formData.main_photo_url;
          }
          b.slots.cover_front = item;
        } else if (b.slots.cover_front.preview || b.slots.cover_front.url) {
          if (!b.slots.cover_front.preview) b.slots.cover_front.preview = b.slots.cover_front.url;
          map.set(b.slots.cover_front.id, b.slots.cover_front);
        } else if (b.formData && b.formData.main_photo_url) {
          b.slots.cover_front.preview = b.formData.main_photo_url;
          b.slots.cover_front.url = b.formData.main_photo_url;
          b.slots.cover_front.cameraOriginal = b.formData.main_photo_url;
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
          if (!p || !p.id) return null;
          p.assignedBookId = b.id;
          p.assignedSlot = s;
          if (map.has(p.id)) {
            const item = map.get(p.id);
            item.assignedBookId = b.id;
            item.assignedSlot = s;
            return item;
          }
          if (p.preview || p.url) {
            if (!p.preview) p.preview = p.url;
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
    if (window.BookStore) {
      const b1 = window.BookStore.createDefaultBook(1, formattedArt);
      b1.formData.article_number = numPart;
      b1.formData.barcode = newBarcode;
      b1.formData.template_mode = window.currentTemplateMode || 'pre2011';
      window.BookStore.init([b1], 1);
    } else {
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
    }

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

  async function calculateNextArticle(offset = null) {
    let globalMax = 0;
    const dbArt = await fetchDbNextArticle();
    if (dbArt) {
      const digits = String(dbArt).replace(/\D/g, '');
      if (digits) globalMax = parseInt(digits, 10);
    }

    let sessionMax = 0;
    if (typeof window.booksSession !== 'undefined' && Array.isArray(window.booksSession)) {
      window.booksSession.forEach(b => {
        if (b.isEditMode) return; // Не учитываем редактируемые старые книги
        const art = (b.formData && (b.formData.article || b.formData.article_number)) || b.article || '';
        const digits = String(art).replace(/\D/g, '');
        if (digits) {
          const val = parseInt(digits, 10);
          if (val < 100000 && val > sessionMax) sessionMax = val;
        }
      });
    }

    let nextNum;
    if (sessionMax > 0) {
      const inc = (offset !== null && offset > 0) ? offset : (offset === 0 ? 0 : 1);
      nextNum = Math.max(globalMax, sessionMax + inc);
    } else {
      const inc = (offset !== null && offset > 0) ? (offset - 1) : 0;
      nextNum = (globalMax > 0 ? globalMax : 1) + inc;
    }

    return `DP-B-${String(nextNum).padStart(5, '0')}`;
  }

  let _checkArtTimeout = null;

  async function checkArticleAvailability(art) {
    const cleanArt = String(art || '').trim();
    const badge = document.getElementById('articleStatusBadge');
    if (!badge || !cleanArt) {
      if (badge) badge.classList.add('hidden');
      return;
    }

    try {
      const res = await fetch(`/api/check_article?article=${encodeURIComponent(cleanArt)}`).then(r => r.json());
      const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
      const isSaved = Boolean(book && book.isSavedToExcel);
      const isEdit = Boolean(book && (book.isEditMode || book.isReopened || isSaved));

      if (res && res.success) {
        badge.classList.remove('hidden');
        if (res.exists) {
          if (isSaved) {
            badge.className = 'text-[10px] font-medium px-2 py-0.5 rounded bg-teal-900/60 text-teal-300 border border-teal-600/50';
            const dispTitle = res.title || (book && book.formData && book.formData.title) || 'Товар';
            badge.innerHTML = `✅ Добавлена в таблицу Ozon («${safeEscape(dispTitle)}»)`;
            badge.onclick = null;
          } else if (isEdit) {
            badge.className = 'text-[10px] font-medium px-2 py-0.5 rounded bg-sky-900/60 text-sky-300 border border-sky-600/50';
            badge.innerHTML = `🔒 Карточка Ozon («${safeEscape(res.title || 'Товар')}»)`;
            badge.onclick = null;
          } else {
            badge.className = 'text-[10px] font-medium px-2 py-0.5 rounded bg-rose-900/70 text-rose-200 border border-rose-500/60 cursor-pointer shadow-sm';
            badge.title = 'Нажмите, чтобы подставить гарантированно свободный артикул';
            badge.innerHTML = `⚠️ Занят («${safeEscape(res.title || 'Товар')}»)! <span class="underline font-bold text-amber-300">Взять ${res.suggested_next_article}</span>`;
            badge.onclick = () => {
              if (typeof window.onArticleInput === 'function') window.onArticleInput(res.suggested_next_article);
            };
          }
        } else {
          badge.className = 'text-[10px] font-medium px-2 py-0.5 rounded bg-emerald-900/60 text-emerald-300 border border-emerald-600/50';
          badge.innerHTML = `✓ Свободен (нет на Ozon)`;
          badge.onclick = null;
        }
      }
    } catch (e) {
      if (badge) badge.classList.add('hidden');
    }
  }

  function safeEscape(str) {
    if (typeof window.escapeHtml === 'function') return window.escapeHtml(str);
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function updateCardModeBanner() {
    try {
      const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
      const isSaved = Boolean(book && book.isSavedToExcel);
      const isEdit = Boolean(book && (book.isEditMode || book.isReopened || isSaved));
      const art = (book && (book.article || (book.formData && book.formData.article))) || document.getElementById('article')?.value || '';

      const banner = document.getElementById('cardModeBanner');
      const dot = document.getElementById('cardModeDot');
      const title = document.getElementById('cardModeTitle');
      const desc = document.getElementById('cardModeDesc');
      const artBadge = document.getElementById('cardModeArticleBadge');
      const cancelBtn = document.getElementById('cardModeCancelBtn');
      const lockIcon = document.getElementById('articleLockIcon');
      const artInput = document.getElementById('article_number');

      const saveBtn = document.getElementById('saveBtn');
      const saveIcon = document.getElementById('saveBtnIcon');
      const saveText = document.getElementById('saveBtnText');
      const secBtns = document.getElementById('editModeSecondaryButtons');

      if (isSaved) {
        if (banner) {
          banner.className = 'mb-5 px-4 py-3 rounded-2xl bg-teal-950/80 border border-teal-500/50 flex flex-wrap items-center justify-between gap-3 text-xs transition-all shadow-sm';
        }
        if (dot) dot.className = 'inline-block w-2.5 h-2.5 rounded-full bg-teal-400';
        if (title) title.innerHTML = `✅ Статус: Книга добавлена в таблицу Ozon <span class="text-white underline">${safeEscape(art)}</span>`;
        if (desc) desc.textContent = '— данные сохранены в таблице и архиве; при повторном сохранении карточка обновится';
        if (artBadge) {
          artBadge.className = 'font-mono text-teal-200 bg-teal-900/50 px-2.5 py-1 rounded-lg border border-teal-600/50 font-bold';
          artBadge.textContent = art || 'В таблице Ozon';
        }
        if (cancelBtn) cancelBtn.classList.remove('hidden');
        if (lockIcon) lockIcon.classList.remove('hidden');
        if (artInput) {
          artInput.readOnly = true;
          artInput.title = 'Карточка сохранена в таблице. Нажмите «Новая книга», чтобы создать новый товар с новым артикулом.';
        }

        if (saveBtn) {
          saveBtn.disabled = false;
          saveBtn.className = 'w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-teal-600 via-emerald-600 to-teal-700 hover:from-teal-500 hover:to-emerald-500 text-white font-bold text-base shadow-xl shadow-teal-600/25 transition flex items-center justify-center gap-2 cursor-pointer';
          saveBtn.innerHTML = `<span id="saveBtnIcon">⚡</span> <span id="saveBtnText">Обновить карточку ${safeEscape(art)} на Ozon (Cmd + Enter)</span>`;
        }
        if (secBtns) secBtns.classList.remove('hidden');

      } else if (isEdit) {
        if (banner) {
          banner.className = 'mb-5 px-4 py-3 rounded-2xl bg-sky-950/80 border border-sky-500/50 flex flex-wrap items-center justify-between gap-3 text-xs transition-all shadow-sm';
        }
        if (dot) dot.className = 'inline-block w-2.5 h-2.5 rounded-full bg-sky-400';
        if (title) title.innerHTML = `✏️ Режим: Редактирование карточки <span class="text-white underline">${safeEscape(art)}</span>`;
        if (desc) desc.textContent = '— правки обновят существующий товар на Ozon без дублирования';
        if (artBadge) {
          artBadge.className = 'font-mono text-sky-200 bg-sky-900/50 px-2.5 py-1 rounded-lg border border-sky-600/50 font-bold';
          artBadge.textContent = art || 'Редактирование';
        }
        if (cancelBtn) cancelBtn.classList.remove('hidden');
        if (lockIcon) lockIcon.classList.remove('hidden');
        if (artInput) {
          artInput.readOnly = true;
          artInput.title = 'В режиме редактирования артикул зафиксирован. Нажмите «Новая книга», чтобы создать новый товар.';
        }

        if (saveBtn) {
          saveBtn.disabled = false;
          saveBtn.className = 'w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-sky-600 via-teal-600 to-sky-700 hover:from-sky-500 hover:to-teal-500 text-white font-bold text-base shadow-xl shadow-sky-600/25 transition flex items-center justify-center gap-2 cursor-pointer';
          saveBtn.innerHTML = `<span id="saveBtnIcon">⚡</span> <span id="saveBtnText">Обновить карточку ${safeEscape(art)} на Ozon (Cmd + Enter)</span>`;
        }
        if (secBtns) secBtns.classList.remove('hidden');

      } else {
        if (banner) {
          banner.className = 'mb-5 px-4 py-3 rounded-2xl bg-emerald-950/60 border border-emerald-500/40 flex flex-wrap items-center justify-between gap-3 text-xs transition-all shadow-sm';
        }
        if (dot) dot.className = 'inline-block w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse';
        if (title) title.textContent = '✨ Режим: Создание новой книги';
        if (desc) desc.textContent = '— книга получит гарантированно уникальный артикул, которого ещё нет на Ozon';
        if (artBadge) {
          artBadge.className = 'font-mono text-emerald-300 bg-emerald-900/50 px-2.5 py-1 rounded-lg border border-emerald-600/40 font-bold';
          artBadge.textContent = art || 'DP-B-?????';
        }
        if (cancelBtn) cancelBtn.classList.add('hidden');
        if (lockIcon) lockIcon.classList.add('hidden');
        if (artInput) {
          artInput.readOnly = false;
          artInput.title = 'Введите номер книги (например 03098)';
        }

        if (saveBtn) {
          saveBtn.disabled = false;
          saveBtn.className = 'w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-emerald-600 via-teal-600 to-emerald-700 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-base shadow-xl shadow-emerald-600/25 transition flex items-center justify-center gap-2 cursor-pointer';
          saveBtn.innerHTML = '<span id="saveBtnIcon">🚀</span> <span id="saveBtnText">Опубликовать новую книгу на Ozon (Cmd + Enter)</span>';
        }
        if (secBtns) secBtns.classList.add('hidden');
      }

      if (art) {
        clearTimeout(_checkArtTimeout);
        _checkArtTimeout = setTimeout(() => checkArticleAvailability(art), 200);
      }
    } catch (bannerErr) {
      console.error('updateCardModeBanner error:', bannerErr);
      const saveBtn = document.getElementById('saveBtn');
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.innerHTML = '<span id="saveBtnIcon">💾</span> <span id="saveBtnText">Записать книгу в таблицу Ozon (Cmd + Enter)</span>';
      }
    }
  }

  async function cancelEditModeAndCreateNew() {
    // 1. Сохраняем состояние текущей редактируемой книги в её объект, НЕ уничтожая её слоты и поля!
    saveCurrentFormToActiveBook();

    // 2. Ищем, есть ли уже чистая пустая вкладка для новой книги в текущей сессии
    const books = window.booksSession || [];
    const isBookEmpty = (b) => {
      if (!b) return true;
      if (b.isEditMode || b.isReopened || b.isSavedToExcel) return false;
      const hasPhotos = b.slots && (
        Boolean(b.slots.cover_front) ||
        (Array.isArray(b.slots.cover_back) && b.slots.cover_back.length > 0) ||
        (Array.isArray(b.slots.info_pages) && b.slots.info_pages.length > 0) ||
        (Array.isArray(b.slots.illustrations) && b.slots.illustrations.length > 0) ||
        (Array.isArray(b.slots.mantra_defects) && b.slots.mantra_defects.length > 0)
      );
      if (hasPhotos) return false;
      const title = (b.formData && b.formData.title) || b.title || '';
      if (title && !title.startsWith('Книга #') && title !== 'Без названия') return false;
      return true;
    };

    const emptyTab = books.find(b => isBookEmpty(b));
    if (emptyTab) {
      switchBook(emptyTab.id);
      if (typeof showToast === 'function') {
        const art = (emptyTab.formData && emptyTab.formData.article) || emptyTab.article || '';
        showToast(`✨ Переключились на чистую карточку <b>${safeEscape(art)}</b>. Прошлая книга сохранена во вкладках.`);
      }
      return;
    }

    // 3. Если пустой вкладки нет — создаем новую отдельную вкладку под гарантированно свободный артикул!
    await addNewBook();

    if (typeof showToast === 'function') {
      const cur = typeof getActiveBook === 'function' ? getActiveBook() : null;
      const art = (cur && (cur.article || (cur.formData && cur.formData.article))) || '';
      showToast(`✨ Создана новая карточка под артикулом <b>${safeEscape(art)}</b>. Прошлая книга сохранена во вкладках.`);
    }
  }

  async function addNewBook() {
    saveCurrentFormToActiveBook();
    const nextArt = await calculateNextArticle(1);
    const nextBarcode = window.BookCalculators
      ? window.BookCalculators.generateEan13FromArticle(nextArt)
      : (window.generateEan13FromArticle ? window.generateEan13FromArticle(nextArt) : '2978470000012');
    const numPart = nextArt.replace(/\D/g, '').slice(-5);

    if (window.BookStore) {
      const newBook = window.BookStore.addBook(nextArt);
      newBook.formData.article_number = numPart;
      newBook.formData.barcode = nextBarcode;
      window.BookStore.syncLegacyGlobals();
    } else {
      const books = window.booksSession || [];
      const nextId = books.length > 0 ? Math.max(...books.map(b => b.id)) + 1 : 1;
      const newBook = {
        id: nextId,
        article: nextArt,
        title: `Книга #${nextId}`,
        isEditMode: false,
        isReopened: false,
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
    }

    renderBooksTabs();
    if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
    if (typeof window.clearForm === 'function') window.clearForm(nextArt);
    updateCardModeBanner();
    scheduleAutoSave();
  }

  function closeBookTab(id, e) {
    if (e) e.stopPropagation();
    const books = window.booksSession || [];
    const targetBook = books.find(b => b.id === id);
    const art = (targetBook && (targetBook.article || (targetBook.formData && targetBook.formData.article))) || `Книга #${id}`;

    const isSaved = Boolean(targetBook && (targetBook.isSavedToExcel || targetBook.isEditMode || targetBook.isReopened));
    const confirmMsg = isSaved
      ? `Закрыть вкладку «${art}»?\n\nКарточка сохранена в базе и таблице Ozon. Вы сможете открыть её снова в любое время из таблицы или каталога.`
      : `Закрыть вкладку «${art}»? Несохраненные данные этой вкладки будут закрыты.`;

    if (!confirm(confirmMsg)) return;

    // ВАЖНО: Фотографии закрываемой книги НЕ возвращаются в общий пул!
    // Общий пул предназначен только для входящих неразобранных фото с телефона/диска.
    // Удаляем из photoPool любые фото, привязанные к закрываемой вкладке:
    window.photoPool = (window.photoPool || []).filter(p => p.assignedBookId !== id);

    if (window.BookStore) {
      window.BookStore.removeBook(id);
    } else {
      window.booksSession = (window.booksSession || []).filter(b => b.id !== id);
      if (window.activeBookId === id) {
        window.activeBookId = window.booksSession.length > 0 ? window.booksSession[0].id : null;
      }
    }

    if ((window.booksSession || []).length === 0) {
      window.activeBookId = null;
      if (window.BookForm && window.BookForm.initialized) {
        window.BookForm.clearForm();
      } else if (typeof window.clearForm === 'function') {
        window.clearForm('');
      }
    }

    if (typeof window.renderPool === 'function') window.renderPool();
    renderBooksTabs();
    restoreFormFromActiveBook();
    if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
    if (typeof window.updateCardModeBanner === 'function') window.updateCardModeBanner();
    scheduleAutoSave();

    if (typeof window.showToast === 'function') {
      const remaining = (window.booksSession || []).length;
      window.showToast(`✕ Вкладка <b>${art}</b> закрыта. (Осталось: ${remaining})`);
    }
  }

  function closeAllBookTabs() {
    const books = window.booksSession || [];
    if (!books || books.length === 0) {
      if (typeof window.showToast === 'function') {
        window.showToast('Вкладок для закрытия нет.', 'info');
      }
      return;
    }

    const count = books.length;
    const confirmMsg = `Закрыть сразу все открытые вкладки книг (${count} шт.)?\n\nСохраненные карточки остаются в базе данных и каталоге.`;
    if (!confirm(confirmMsg)) return;

    // Очищаем привязки фото закрытых книг
    const bookIds = new Set(books.map(b => b.id));
    window.photoPool = (window.photoPool || []).filter(p => !bookIds.has(p.assignedBookId));

    if (window.BookStore) {
      window.BookStore.removeAllBooks();
    } else {
      window.booksSession = [];
      window.activeBookId = null;
    }

    if (window.BookForm && window.BookForm.initialized) {
      window.BookForm.clearForm();
    } else if (typeof window.clearForm === 'function') {
      window.clearForm('');
    }

    if (typeof window.renderPool === 'function') window.renderPool();
    renderBooksTabs();
    restoreFormFromActiveBook();
    if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
    if (typeof window.updateCardModeBanner === 'function') window.updateCardModeBanner();
    scheduleAutoSave();

    if (typeof window.showToast === 'function') {
      window.showToast(`✕ Все вкладки (${count} шт.) успешно закрыты.`, 'success');
    }
  }

  function deleteBookSession(id, e) {
    return closeBookTab(id, e);
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
    if (fullArt) {
      clearTimeout(_checkArtTimeout);
      _checkArtTimeout = setTimeout(() => checkArticleAvailability(fullArt), 250);
    }
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
        checkArticleAvailability(fullArt);
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
    checkArticleAvailability(fullArt);
  }

  function onBarcodeInput(val) {
    const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
    if (!book) return;
    if (!book.formData) book.formData = {};
    book.formData.barcode = val.trim();
    scheduleAutoSave();
  }

  function onTitleInput(val) {
    if (window.BookStore) {
      window.BookStore.setField('title', val);
    }
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

    if (window.BookForm && window.BookForm.initialized) {
      const data = window.BookForm.readForm();
      Object.assign(book.formData, data);
      if (window.BookStore) {
        window.BookStore.updateFields(data, book.id);
      }
    } else {
      FORM_FIELD_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
          book.formData[id] = el.value;
          if (window.BookStore) {
            window.BookStore.setField(id, el.value, book.id);
          }
        }
      });
      if (document.getElementById('autoPackageAdder')) {
        book.formData.auto_package_adder = document.getElementById('autoPackageAdder').checked;
        if (window.BookStore) window.BookStore.setField('auto_package_adder', book.formData.auto_package_adder, book.id);
      }
    }

    const rawY = parseInt(document.getElementById('year')?.value, 10);
    if (!isNaN(rawY) && rawY > 1000 && rawY < 2100) {
      book.formData.template_mode = (rawY <= 2011) ? 'pre2011' : 'post2011';
    } else {
      book.formData.template_mode = window.currentTemplateMode || 'pre2011';
    }
    if (window.BookStore) window.BookStore.setField('template_mode', book.formData.template_mode, book.id);
    if (book.formData.article) book.article = book.formData.article;
    if (book.formData.title) book.title = book.formData.title;
  }

  function restoreFormFromActiveBook() {
    const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
    if (!book) return;
    if (!book.formData) book.formData = {};

    if (window.BookForm && window.BookForm.initialized) {
      window.BookForm.populateForm(book.formData, { force: true });
    } else {
      FORM_FIELD_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
          let val = (book.formData[id] !== undefined && book.formData[id] !== null) ? String(book.formData[id]) : '';
          if (id === 'dimensions' && val.includes('[object')) {
            val = '';
          }
          el.value = val;
        }
      });
      if (document.getElementById('autoPackageAdder')) {
        document.getElementById('autoPackageAdder').checked = (book.formData.auto_package_adder !== false);
      }
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
    const isManual = Boolean(book.formData && book.formData.is_manual_condition);
    const savedCond = book.formData && book.formData.condition;
    if (typeof window.setCondition === 'function') {
      if (defectCount > 0) {
        if (savedCond === 'Удовлетворительная') {
          window.setCondition('Удовлетворительная', false);
        } else {
          window.setCondition('Хорошая', false);
        }
      } else {
        if (savedCond === 'Хорошая' || savedCond === 'Удовлетворительная') {
          if (book.formData) book.formData.is_manual_condition = true;
          window.setCondition(savedCond, false);
        } else {
          window.setCondition('Очень хорошая', false);
        }
      }
    }
    const yParsed = parseInt(book.formData.year, 10);
    const mode = (!isNaN(yParsed) && yParsed > 1000 && yParsed < 2100)
      ? (yParsed <= 2011 ? 'pre2011' : 'post2011')
      : (book.formData.template_mode || 'pre2011');
    book.formData.template_mode = mode;
    if (typeof window.setTemplateMode === 'function') {
      window.setTemplateMode(mode, false);
    }
    if (typeof window.updateDimensionsPreviewBadge === 'function') {
      window.updateDimensionsPreviewBadge();
    }
    if (typeof window.syncAnnotationWarningWithDefectsSlot === 'function') {
      window.syncAnnotationWarningWithDefectsSlot();
    }
    try {
      updateCardModeBanner();
    } catch (eBanner) {
      console.error('updateCardModeBanner error during restore:', eBanner);
    }

    const fs = document.getElementById('formStatus');
    if (fs) {
      if (book.isAiRecognizing) {
        fs.textContent = '⏳ Данные этой книги сейчас распознаются нейросетью Gemini...';
        fs.className = 'text-center text-xs text-amber-400 font-semibold animate-pulse';
      } else if (book.isAiRecognized) {
        fs.textContent = `✓ Данные книги «${book.formData?.title || book.title || 'Книга'}» распознаны ИИ`;
        fs.className = 'text-center text-xs text-emerald-400 font-semibold';
      } else if (book.isSavedToExcel) {
        fs.textContent = `✅ Книга сохранена в Excel`;
        fs.className = 'text-center text-xs text-teal-400 font-semibold';
      } else {
        fs.textContent = 'Записывает в активную рабочую таблицу и синхронизирует с Ozon';
        fs.className = 'text-center text-xs text-slate-500';
      }
    }
  }

  function switchBook(id) {
    const targetId = Number(id);
    if (window.activeBookId === targetId) return;
    saveCurrentFormToActiveBook();
    if (window.BookStore) {
      window.BookStore.switchActiveBook(targetId);
    } else {
      window.activeBookId = targetId;
    }

    const newActiveBook = (window.booksSession || []).find(b => b.id === targetId);
    window.isBookAiRecognizing = Boolean(newActiveBook && newActiveBook.isAiRecognizing);

    // Гарантированно сбрасываем залипшую кнопку сохранения предыдущей книги
    const saveBtn = document.getElementById('saveBtn');
    if (saveBtn) {
      saveBtn.disabled = false;
      const isSaved = Boolean(newActiveBook && (newActiveBook.isSavedToExcel || newActiveBook.isEditMode || newActiveBook.isReopened));
      const curArt = (newActiveBook && (newActiveBook.article || (newActiveBook.formData && newActiveBook.formData.article))) || '';
      if (isSaved) {
        saveBtn.innerHTML = `<span id="saveBtnIcon">💾</span> <span id="saveBtnText">Сохранить изменения книги ${safeEscape(curArt)} в Excel, Ozon и БД (Cmd + Enter)</span>`;
      } else {
        saveBtn.innerHTML = '<span id="saveBtnIcon">✨</span> <span id="saveBtnText">Записать новую книгу в таблицу Ozon (Cmd + Enter)</span>';
      }
    }

    renderBooksTabs();
    restoreFormFromActiveBook();
    if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
    if (typeof window.updateAiBatchBtnState === 'function') window.updateAiBatchBtnState();
    if (typeof window.updateCardModeBanner === 'function') window.updateCardModeBanner();
    if (typeof window.renderPool === 'function') window.renderPool();
    scheduleAutoSave();
  }

  function renderBooksTabs() {
    const container = document.getElementById('booksTabsContainer');
    if (!container) return;
    const titleEl = document.getElementById('activeBookTitle');

    const books = window.booksSession || [];
    if (books.length === 0) {
      container.innerHTML = `
        <div class="flex items-center gap-2 py-1.5 px-3.5 rounded-xl bg-slate-900/90 border border-slate-800 text-xs text-slate-400 shadow-sm">
          <span>📭 Все вкладки закрыты (0 открытых книг).</span>
          <button type="button" onclick="addNewBook()" class="text-amber-400 hover:text-amber-300 font-bold hover:underline flex items-center gap-1">
            <span>+ Создать книгу</span>
          </button>
        </div>
      `;
      if (titleEl) {
        titleEl.innerHTML = '📚 <span class="text-slate-500 font-mono">[Нет активной книги]</span>';
      }
      return;
    }

    const anyBackgroundAi = books.some(b => b.isAiRecognizing && b.id !== window.activeBookId);

    container.innerHTML = books.map(b => {
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

      const statusIcon = b.isAiRecognizing
        ? '<span class="inline-block animate-spin mr-0.5">⏳</span>'
        : (b.isAiRecognized ? '✨' : (b.isSavedToExcel ? '✅' : '📖'));

      return `
        <div class="inline-flex items-center rounded-xl overflow-hidden border transition ${isActive ? 'border-amber-500 bg-amber-500 text-slate-950 font-bold shadow-md shadow-amber-500/20' : (b.isAiRecognizing ? 'border-amber-400/80 bg-amber-950/40 text-amber-200' : 'border-slate-700 bg-slate-800 hover:bg-slate-750 text-slate-300')}">
          <button type="button" onclick="switchBook(${b.id})" class="px-3 py-1.5 text-xs font-semibold flex items-center gap-2 text-left" title="${b.isAiRecognizing ? 'Книга сейчас анализируется нейросетью Gemini...' : (b.isAiRecognized ? 'Книга успешно распознана нейросетью!' : '')}">
            <span>${statusIcon} <span class="font-mono tracking-tight font-bold">${art}</span><span class="opacity-80">${titleSnippet}</span></span>
            <span class="px-1.5 py-0.2 rounded-full text-[10px] ${isActive ? 'bg-slate-950 text-amber-300' : 'bg-slate-900 text-slate-400'} font-mono">${count} фото</span>
            ${b.isAiRecognizing ? '<span class="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping inline-block"></span>' : ''}
          </button>
          <button type="button" onclick="closeBookTab(${b.id}, event)" class="px-2 py-1.5 text-xs ${isActive ? 'text-slate-950 hover:bg-amber-400 hover:text-rose-950' : 'text-slate-400 hover:bg-slate-700 hover:text-rose-400'} transition font-bold" title="Закрыть вкладку этой книги">✕</button>
        </div>
      `;
    }).join('');

    const cur = typeof getActiveBook === 'function' ? getActiveBook() : null;
    if (titleEl) {
      if (cur) {
        const curArt = (cur.formData && cur.formData.article) || cur.article || `Книга #${cur.id}`;
        const isReopened = Boolean(cur.isReopened);
        const isCurRecognizing = Boolean(cur.isAiRecognizing);

        let statusPill = '';
        if (isCurRecognizing) {
          statusPill = '<span class="ml-2 px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/50 text-[10px] font-bold animate-pulse">⏳ Идет анализ Gemini...</span>';
        } else if (anyBackgroundAi) {
          const bgBook = (window.booksSession || []).find(b => b.isAiRecognizing && b.id !== cur.id);
          const bgArt = bgBook ? ((bgBook.formData && bgBook.formData.article) || bgBook.article || `#${bgBook.id}`) : '';
          statusPill = `<span class="ml-2 px-2 py-0.5 rounded bg-violet-950/70 text-violet-300 border border-violet-700/60 text-[10px] font-semibold animate-pulse">⚡ [${bgArt}] анализируется в фоне...</span>`;
        } else if (isReopened) {
          statusPill = '<span class="ml-1.5 px-2 py-0.5 rounded bg-sky-950 text-sky-300 border border-sky-600/60 text-[10px] font-bold">Из каталога</span>';
        }

        titleEl.innerHTML = `📚 <span class="font-mono text-white">[${curArt}]</span>: Слоты категорий ${statusPill}`;
      } else {
        titleEl.innerHTML = '📚 <span class="text-slate-500 font-mono">[Нет активной книги]</span>';
      }
    }
  }

  // Сохранение черновика при закрытии или перезагрузке страницы
  window.addEventListener('beforeunload', () => {
    try {
      saveCurrentFormToActiveBook();
      const payload = {
        has_draft: true,
        activeBookId: window.activeBookId,
        booksSession: window.booksSession,
        photoPool: (window.photoPool || []).map(p => ({
          id: p.id,
          name: p.name,
          mime: p.mime,
          preview: p.preview,
          cameraOriginal: p.cameraOriginal,
          rawOriginal: p.rawOriginal,
          croppedBase: p.croppedBase,
          assignedBookId: p.assignedBookId,
          assignedSlot: p.assignedSlot
        })),
        timestamp: Date.now()
      };
      localStorage.setItem('bookinistic_session_draft', JSON.stringify(payload));
    } catch (e) {}
  });

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
  window.checkArticleAvailability = checkArticleAvailability;
  window.updateCardModeBanner = updateCardModeBanner;
  window.cancelEditModeAndCreateNew = cancelEditModeAndCreateNew;
  window.addNewBook = addNewBook;
  window.closeBookTab = closeBookTab;
  window.closeAllBookTabs = closeAllBookTabs;
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

