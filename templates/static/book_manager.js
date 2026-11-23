/**
 * book_manager.js: Управление формой книги, валидация полей, обогащение из FantLab,
 * расчет габаритов, сохранности, цен и оркестрация сохранения книги в Excel/Vault.
 *
 * Выделенные модули:
 * - modules/barcode_modal.js   : Модальное окно и генерация штрихкодов EAN-13
 * - modules/preview_table.js   : Предпросмотр таблицы Excel, скачивание и удаление
 * - modules/system_modals.js   : Памятки, справки, ключи Gemini и Ozon API
 * - modules/session_tabs.js    : Сессии книг, переключение вкладок и автосохранение
 * - core/calculators.js        : Чистые функции расчета габаритов ГОСТ и сохранности
 */

(function (window) {
  'use strict';

  // -------------------------------------------------------------
  // РЕЖИМЫ ШАБЛОНА: ДО 2011 ИЛИ ПОСЛЕ 2011 ГОДА
  // -------------------------------------------------------------
  function setTemplateMode(mode, userInitiated = true) {
    if (userInitiated) {
      if (mode === window.currentTemplateMode) return;
      const yearInput = document.getElementById('year');
      const rawYear = yearInput ? yearInput.value.trim() : '';
      const y = parseInt(rawYear, 10);
      if (!isNaN(y) && y > 1000 && y < 2100) {
        if (y <= 2011 && mode === 'post2011') {
          const ok = confirm(`⚠️ Внимание! Для книги в поле «Год выпуска» указан ${y} год издания (до 2011 г.).\n\nПо регламенту Ozon книги до 2011 года включительно оформляются по шаблону «До 2011 г.» (без обязательного ISBN).\n\nВы действительно хотите переключить форму на «После 2011 г.»?\n(При нажатии ОК форма переключится, а несовпадающий год будет очищен для ввода актуального).`);
          if (!ok) {
            if (yearInput) {
              yearInput.focus();
              yearInput.classList.add('ring-2', 'ring-rose-500', 'border-rose-500');
              setTimeout(() => yearInput.classList.remove('ring-2', 'ring-rose-500', 'border-rose-500'), 2500);
            }
            return;
          }
          if (yearInput) yearInput.value = '';
        }
        if (y > 2011 && mode === 'pre2011') {
          const ok = confirm(`⚠️ Внимание! Для книги в поле «Год выпуска» указан ${y} год издания (после 2011 г.).\n\nПо регламенту Ozon книги после 2011 года требуют обязательный ISBN и шаблон «После 2011 г.».\n\nВы действительно хотите переключить форму на «До 2011 г.»?\n(При нажатии ОК форма переключится, а несовпадающий год будет очищен для ввода актуального).`);
          if (!ok) {
            if (yearInput) {
              yearInput.focus();
              yearInput.classList.add('ring-2', 'ring-rose-500', 'border-rose-500');
              setTimeout(() => yearInput.classList.remove('ring-2', 'ring-rose-500', 'border-rose-500'), 2500);
            }
            return;
          }
          if (yearInput) yearInput.value = '';
        }
      }
    }

    window.currentTemplateMode = (mode === 'post2011') ? 'post2011' : 'pre2011';
    const btnPre = document.getElementById('btnModePre');
    const btnPost = document.getElementById('btnModePost');
    const isbnStar = document.getElementById('isbnStar');
    const isbnNote = document.getElementById('isbnNote');
    const isbnInput = document.getElementById('isbn');
    const modeBadge = document.getElementById('templateModeBadge');
    const modeText = document.getElementById('templateModeText');

    if (window.currentTemplateMode === 'pre2011') {
      if (modeBadge) {
        modeBadge.className = 'text-[11px] font-mono px-3 py-1 rounded-xl bg-amber-950/60 border border-amber-800/80 text-amber-300 font-semibold flex items-center gap-1.5';
      }
      if (modeText) {
        modeText.textContent = 'Ozon: До 2011 г. (ISBN опционален)';
      }
      if (btnPre) {
        btnPre.className = 'px-2.5 py-1 text-xs font-semibold rounded-lg transition bg-amber-600 text-white shadow-sm flex items-center gap-1';
      }
      if (btnPost) {
        btnPost.className = 'px-2.5 py-1 text-xs font-medium rounded-lg transition text-slate-400 hover:text-white flex items-center gap-1';
      }
      if (isbnStar) isbnStar.classList.add('hidden');
      if (isbnNote) {
        isbnNote.textContent = '(необязателен до 2011 г.)';
        isbnNote.className = 'text-[10px] text-amber-400/80 font-normal';
      }
      if (isbnInput) {
        isbnInput.placeholder = 'Необязательно для книг до 2011 г.';
        if (isbnInput.value === '978-5-0000-0000-0') isbnInput.value = '';
      }
    } else {
      if (modeBadge) {
        modeBadge.className = 'text-[11px] font-mono px-3 py-1 rounded-xl bg-emerald-950/60 border border-emerald-800/80 text-emerald-300 font-semibold flex items-center gap-1.5';
      }
      if (modeText) {
        modeText.textContent = 'Ozon: После 2011 г. (ISBN обязателен)';
      }
      if (btnPre) {
        btnPre.className = 'px-2.5 py-1 text-xs font-medium rounded-lg transition text-slate-400 hover:text-white flex items-center gap-1';
      }
      if (btnPost) {
        btnPost.className = 'px-2.5 py-1 text-xs font-semibold rounded-lg transition bg-emerald-600 text-white shadow-sm flex items-center gap-1';
      }
      if (isbnStar) isbnStar.classList.remove('hidden');
      if (isbnNote) {
        isbnNote.textContent = '(обязательное поле)';
        isbnNote.className = 'text-[10px] text-rose-400 font-normal';
      }
      if (isbnInput) {
        isbnInput.placeholder = '978-5-0000-0000-0';
        if (!isbnInput.value.trim()) isbnInput.value = '978-5-0000-0000-0';
      }
    }

    const book = typeof window.getActiveBook === 'function' ? window.getActiveBook() : null;
    if (book) {
      if (!book.formData) book.formData = {};
      book.formData.template_mode = window.currentTemplateMode;
    }
    if (typeof window.switchPreviewTable === 'function') {
      window.switchPreviewTable(window.currentTemplateMode, false);
    }
    if (typeof window.scheduleAutoSave === 'function') {
      window.scheduleAutoSave();
    }
  }

  function onYearInput(val) {
    autoDetectCountry();
    const y = parseInt(val, 10);
    if (!isNaN(y) && y > 1000 && y < 2100) {
      const targetMode = window.BookValidators
        ? window.BookValidators.resolveTemplateMode(y)
        : ((y <= 2011) ? 'pre2011' : 'post2011');
      if (targetMode !== window.currentTemplateMode) {
        setTemplateMode(targetMode, false);
        if (typeof window.switchPreviewTable === 'function') {
          window.switchPreviewTable(targetMode, true);
        }
      }
    }
  }

  // -------------------------------------------------------------
  // ОБОГАЩЕНИЕ ДАННЫХ ИЗ БИБЛИОГРАФИЧЕСКОЙ БАЗЫ FANTLAB
  // -------------------------------------------------------------
  async function runManualEnrichment() {
    const title = document.getElementById('title')?.value?.trim() || '';
    const isbn = document.getElementById('isbn')?.value?.trim() || '';
    if (!title && !isbn) {
      alert('Укажите название книги или ISBN для сверки с базой FantLab!');
      return;
    }
    const curBook = typeof window.getActiveBook === 'function' ? window.getActiveBook() : null;
    const hasIllustrations = curBook && curBook.slots && curBook.slots.illustrations && curBook.slots.illustrations.length > 0;

    const bookPayload = {
      title: title,
      isbn: isbn,
      author: document.getElementById('author')?.value?.trim() || document.getElementById('author_cover')?.value?.trim() || '',
      year: document.getElementById('year')?.value?.trim() || '',
      publisher: document.getElementById('publisher')?.value?.trim() || '',
      illustrator: document.getElementById('illustrator')?.value?.trim() || '',
      series: document.getElementById('series')?.value?.trim() || '',
      original_title: document.getElementById('original_title')?.value?.trim() || '',
      pages: document.getElementById('pages')?.value?.trim() || ''
    };

    const fs = document.getElementById('formStatus');
    if (fs) {
      fs.textContent = isbn ? `🔍 Поиск в базе FantLab по ISBN [${isbn}]...` : '🔍 Поиск в библиографической базе FantLab...';
      fs.className = 'text-center text-xs text-cyan-400 font-semibold';
    }

    try {
      const json = window.ApiClient
        ? await window.ApiClient.enrichBook(bookPayload, hasIllustrations, true)
        : await fetch('/api/enrich_metadata', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ book: bookPayload, has_illustrations: hasIllustrations, fantlab_lookup: true })
          }).then(r => r.json());

      if (json.success && json.data) {
        // Строго исключаем цену, аннотацию и размеры из перезаписи при ручной сверке
        delete json.data.price;
        delete json.data.suggested_price;
        delete json.data.old_price;
        delete json.data.annotation;
        delete json.data.width;
        delete json.data.length;
        delete json.data.height;
        delete json.data.width_mm;
        delete json.data.length_mm;
        delete json.data.height_mm;
        delete json.data.weight;
        delete json.data.weight_g;
        delete json.data.dimensions;

        populateFields(json.data, curBook);

        if (json.data.exact_isbn_match) {
          const matchedIsbn = json.data.isbn || isbn;
          const successMsg = `✓ 100% совпадение по ISBN [${matchedIsbn}]: поля книги уточнены через FantLab!`;
          if (fs) {
            fs.textContent = successMsg;
            fs.className = 'text-center text-xs text-emerald-400 font-bold';
          }
          if (typeof window.showToast === 'function') window.showToast(`🎯 FantLab: карточка уточнена по ISBN ${matchedIsbn}`);
        } else {
          const vSource = json.data.verified_by || 'База проверена';
          if (fs) {
            fs.textContent = `✓ Данные сверены с базой (${vSource}), недостающие поля дополнены.`;
            fs.className = 'text-center text-xs text-cyan-400 font-semibold';
          }
          if (typeof window.showToast === 'function') window.showToast(`✓ Сверка с базой завершена (${vSource})`);
        }
      } else {
        if (fs) {
          fs.textContent = 'ℹ️ Точных совпадений в базе FantLab не найдено.';
          fs.className = 'text-center text-xs text-slate-400 font-medium';
        }
        if (typeof window.showToast === 'function') window.showToast('ℹ️ В базе FantLab совпадений не найдено');
      }
    } catch (err) {
      console.error('Ошибка в runManualEnrichment:', err);
      if (fs) {
        fs.textContent = '⚠️ Не удалось связаться с базой.';
        fs.className = 'text-center text-xs text-rose-400';
      }
      if (typeof window.showToast === 'function') window.showToast('⚠️ Ошибка соединения с FantLab');
    }
  }

  // -------------------------------------------------------------
  // ЗАПОЛНЕНИЕ ПОЛЕЙ КАРТОЧКИ ТОВАРА (POPULATE FIELDS)
  // -------------------------------------------------------------
  function populateFields(data, targetBook = null) {
    if (!data) return;
    const curBookObj = targetBook || (typeof window.getActiveBook === 'function' ? window.getActiveBook() : null);
    if (!curBookObj) return;
    if (!curBookObj.formData) curBookObj.formData = {};

    const isCurrentActive = (curBookObj.id === window.activeBookId);

    try {
      const fill = (id, val, allowEmpty = false) => {
        if (val === undefined || val === null) return;
        const sVal = String(val);
        if (!allowEmpty && sVal.trim() === '') return;
        curBookObj.formData[id] = sVal;
        if (isCurrentActive) {
          const el = document.getElementById(id);
          if (el) {
            el.value = sVal;
            el.classList.add('field-updated');
            setTimeout(() => el.classList.remove('field-updated'), 1200);
          }
        }
      };

      const normAuth = (a) => {
        if (!a || typeof a !== 'string') return '';
        const trimmed = a.trim();
        if (['автор не указан', 'нет автора', 'неизвестен', 'нет', 'отсутствует', 'не указан'].includes(trimmed.toLowerCase())) {
          return 'не указан';
        }
        return trimmed;
      };
      const cleanPub = (p) => {
        if (!p || typeof p !== 'string') return '';
        return (typeof window.cleanPublisherName === 'function') ? window.cleanPublisherName(p) : p.trim();
      };

      if (data.title) fill('title', data.title);
      if (data.original_title) fill('original_title', data.original_title);
      if (data.author_cover) fill('author_cover', normAuth(data.author_cover));
      if (data.author || data.author_cover) fill('author', normAuth(data.author || data.author_cover));
      if (data.publisher) fill('publisher', cleanPub(data.publisher));

      // Бренд Ozon: сопоставление с реестром Ozon
      const pubForBrand = data.publisher || (isCurrentActive ? document.getElementById('publisher')?.value : (curBookObj.formData && curBookObj.formData.publisher)) || '';
      let targetBrand = data.brand;
      if (!targetBrand || targetBrand === 'Нет бренда' || targetBrand.toLowerCase() === 'не указан') {
        targetBrand = (typeof window.resolveBrandFromPublisher === 'function') ? window.resolveBrandFromPublisher(pubForBrand) : 'Нет бренда';
      } else {
        const verified = (typeof window.resolveBrandFromPublisher === 'function') ? window.resolveBrandFromPublisher(targetBrand) : targetBrand;
        targetBrand = (verified !== 'Нет бренда') ? verified : ((typeof window.resolveBrandFromPublisher === 'function') ? window.resolveBrandFromPublisher(pubForBrand) : 'Нет бренда');
      }
      fill('brand', targetBrand || 'Нет бренда');

      const recognizedYear = data.year ? parseInt(data.year, 10) : 0;
      if (data.year) {
        fill('year', data.year);
        if (!isNaN(recognizedYear) && recognizedYear > 1000 && recognizedYear < 2100) {
          const autoMode = (recognizedYear <= 2011) ? 'pre2011' : 'post2011';
          curBookObj.formData.template_mode = autoMode;
          if (isCurrentActive) {
            try { setTemplateMode(autoMode, false); } catch (e) { console.warn('setTemplateMode error', e); }
          }
        }
      }

      // Правило: книги до 2011 года без 100% подтверждения на фото не требуют ISBN
      const isPre2011 = (recognizedYear > 0 && recognizedYear <= 2011) || ((curBookObj.formData.template_mode || window.currentTemplateMode) === 'pre2011');
      let cleanIsbn = data.isbn ? String(data.isbn).trim() : '';
      const is100PercentOnPhoto = !!data.isbn_100_percent_on_photo;

      if (isPre2011 && !is100PercentOnPhoto && !data.exact_isbn_match) {
        cleanIsbn = '';
      }
      if (recognizedYear > 0 && recognizedYear < 1987 && !data.exact_isbn_match) {
        cleanIsbn = ''; // В СССР до 1987 г. ISBN не существовало
      }

      if (cleanIsbn) {
        fill('isbn', cleanIsbn);
      } else if (data.exact_isbn_match && data.isbn) {
        fill('isbn', data.isbn);
      } else if (window.currentTemplateMode === 'post2011') {
        fill('isbn', '978-5-0000-0000-0');
      } else if (data.isbn !== undefined) {
        fill('isbn', '', true);
      }

      let bcVal = data.barcode ? String(data.barcode).trim() : '';
      if (!bcVal || bcVal === 'генерирует озон' || !/^\d{12,13}$/.test(bcVal)) {
        const curArt = curBookObj.formData.article || curBookObj.article || 'DP-B-00001';
        bcVal = window.BookCalculators
          ? window.BookCalculators.generateEan13FromArticle(curArt)
          : (window.generateEan13FromArticle ? window.generateEan13FromArticle(curArt) : '2978470000012');
      }
      fill('barcode', bcVal);
      if (data.series) fill('series', data.series);
      if (data.pages) fill('pages', data.pages);

      // Аннотация с префиксом предупреждения при наличии дефектов
      if (data.annotation !== undefined && data.annotation !== null) {
        const incomingAnt = String(data.annotation).trim();
        if (incomingAnt) {
          let cleanAnt = typeof window.cleanAnnotationText === 'function' ? window.cleanAnnotationText(incomingAnt) : incomingAnt;
          const hasMantraDefects = Boolean(curBookObj.slots && curBookObj.slots.mantra_defects && curBookObj.slots.mantra_defects.length > 0);
          let fullAnt = cleanAnt;
          if (hasMantraDefects && cleanAnt) {
            fullAnt = (window.ANNOTATION_WARNING || 'ВНИМАНИЕ! КНИГА НЕ НОВАЯ. Имеются определённые нюансы (повреждения) см. дополнительные фото.') + '\n\n' + cleanAnt;
          }
          curBookObj.formData.annotation = fullAnt;
          if (isCurrentActive) {
            const antEl = document.getElementById('annotation');
            if (antEl) {
              antEl.value = fullAnt;
              antEl.classList.add('field-updated');
              setTimeout(() => antEl.classList.remove('field-updated'), 1200);
            }
            if (typeof window.syncAnnotationWarningWithDefectsSlot === 'function') {
              window.syncAnnotationWarningWithDefectsSlot();
            }
          }
        }
      }

      if (data.translator) fill('translator', data.translator);

      // Иллюстратора указываем только при наличии фото в слоте иллюстраций
      const hasIllustrationsPhotos = curBookObj.slots && curBookObj.slots.illustrations && curBookObj.slots.illustrations.length > 0;
      if (!hasIllustrationsPhotos) {
        fill('illustrator', '', true);
        if (isCurrentActive) {
          const illEl = document.getElementById('illustrator');
          if (illEl) illEl.value = '';
        }
      } else if (data.illustrator) {
        fill('illustrator', data.illustrator);
      }

      fill('hashtags', '');
      const ageVal = (data.age_limit || '').trim();
      fill('age_limit', ageVal);
      if (isCurrentActive) {
        const ageEl = document.getElementById('age_limit');
        if (ageEl) {
          ageEl.value = ageVal;
          if (ageVal) {
            ageEl.classList.add('field-updated');
            setTimeout(() => ageEl.classList.remove('field-updated'), 1200);
          }
        }
      }

      if (data.cover_type) fill('cover_type', data.cover_type);

      if (data.genre) {
        const rawG = String(data.genre).trim();
        const curTitle = data.title || (curBookObj.formData && curBookObj.formData.title) || '';
        const curAnnot = data.annotation || (curBookObj.formData && curBookObj.formData.annotation) || '';
        const resolvedGenre = (typeof window.resolveOzonGenre === 'function')
          ? window.resolveOzonGenre(rawG, curTitle, curAnnot)
          : rawG;
        fill('genre', resolvedGenre);
        if (isCurrentActive) {
          const genreEl = document.getElementById('genre');
          if (genreEl) {
            let matched = false;
            for (let opt of genreEl.options) {
              if (opt.value === resolvedGenre || opt.text === resolvedGenre) {
                genreEl.value = opt.value;
                matched = true;
                break;
              }
            }
            if (!matched && typeof resolvedGenre === 'string' && resolvedGenre.trim() && resolvedGenre !== 'Детская литература') {
              const opt = document.createElement('option');
              opt.value = resolvedGenre;
              opt.textContent = resolvedGenre;
              genreEl.appendChild(opt);
              genreEl.value = resolvedGenre;
            } else if (!matched) {
              genreEl.value = 'Проза';
            }
            try { handleGenreChange(); } catch (e) { console.warn('handleGenreChange error', e); }
          }
        }
      }

      if (data.paper_type) fill('paper_type', data.paper_type);
      if (data.condition) {
        const defectCount = (curBookObj.slots && curBookObj.slots.mantra_defects) ? curBookObj.slots.mantra_defects.length : 0;
        let condToSet = data.condition;
        if (defectCount === 0) {
          condToSet = 'Очень хорошая';
        } else if (condToSet !== 'Удовлетворительная') {
          condToSet = 'Хорошая';
        }
        curBookObj.formData.condition = condToSet;
        if (isCurrentActive) {
          try { setCondition(condToSet, false); } catch (e) { console.warn('setCondition error', e); }
        }
      }
      if (data.suggested_price) {
        const p = parseInt(data.suggested_price, 10);
        if (!isNaN(p) && p > 0) {
          curBookObj.formData.price = String(p);
          curBookObj.formData.old_price = String(Math.round(p * 1.4));
          if (isCurrentActive) {
            try { setPrice(p); } catch (e) { console.warn('setPrice error', e); }
          }
        }
      }

      if (data.width_mm && data.length_mm && data.height_mm) {
        curBookObj.formData.width = String(data.width_mm);
        curBookObj.formData.length = String(data.length_mm);
        curBookObj.formData.height = String(data.height_mm);
        curBookObj.formData.dimensions = `${data.width_mm}x${data.length_mm}x${data.height_mm}`;
        if (isCurrentActive) {
          if (document.getElementById('width')) document.getElementById('width').value = data.width_mm;
          if (document.getElementById('length')) document.getElementById('length').value = data.length_mm;
          if (document.getElementById('height')) document.getElementById('height').value = data.height_mm;
          try { onDimensionChange(); } catch (e) { console.warn('onDimensionChange error', e); }
        }
      }
      if (data.weight_g) {
        curBookObj.formData.weight = String(data.weight_g);
        if (isCurrentActive && document.getElementById('weight')) {
          document.getElementById('weight').value = data.weight_g;
        }
      }

      if (isCurrentActive) {
        try { autoDetectCountry(); } catch (e) { console.warn('autoDetectCountry error', e); }
        if (typeof window.saveCurrentFormToActiveBook === 'function') {
          try { window.saveCurrentFormToActiveBook(); } catch (e) { console.warn('saveCurrentFormToActiveBook error', e); }
        }
      }
      if (typeof window.renderBooksTabs === 'function') {
        try { window.renderBooksTabs(); } catch (e) { console.warn('renderBooksTabs error', e); }
      }
      if (typeof window.scheduleAutoSave === 'function') {
        try { window.scheduleAutoSave(); } catch (e) { console.warn('scheduleAutoSave error', e); }
      }
    } catch (err) {
      console.error('Ошибка в populateFields:', err);
    }
  }

  // -------------------------------------------------------------
  // ЦЕНЫ И СОХРАННОСТЬ
  // -------------------------------------------------------------
  function setPrice(p) {
    const priceEl = document.getElementById('price');
    if (priceEl) priceEl.value = p;
    calcOldPrice();
  }

  function calcOldPrice() {
    const priceEl = document.getElementById('price');
    const p = parseFloat(priceEl?.value) || 0;
    const old = window.BookCalculators
      ? window.BookCalculators.calcOldPrice(p)
      : Math.max(Math.round((p * 1.4) / 10) * 10, Math.round(p + 50));
    const oldPriceEl = document.getElementById('old_price');
    if (oldPriceEl) oldPriceEl.value = old > 0 ? old : '';
  }

  function setCondition(cond, isUserManual = false) {
    const curBook = typeof window.getActiveBook === 'function' ? window.getActiveBook() : null;
    const defectCount = (curBook && curBook.slots && curBook.slots.mantra_defects) ? curBook.slots.mantra_defects.length : 0;
    const hasDefects = defectCount > 0;

    let normalized = cond || 'Очень хорошая';
    if (normalized === 'Отличная' || normalized === 'Очень хорошее') normalized = 'Очень хорошая';
    if (normalized === 'Хорошее') normalized = 'Хорошая';
    if (normalized === 'Удовлетворительное') normalized = 'Удовлетворительная';
    if (normalized === 'Плохая' || normalized === 'Плохое') normalized = 'Хорошая';

    if (hasDefects) {
      // Если есть фото в слоте [5. Дефекты], сохранность не может быть «Очень хорошая»
      if (normalized === 'Очень хорошая') {
        if (isUserManual && typeof window.showToast === 'function') {
          window.showToast('⚠️ В слоте [5. Дефекты] есть фото: сохранность не может быть «Очень хорошее».');
        }
        normalized = 'Хорошая';
      }
      if (curBook) {
        if (!curBook.formData) curBook.formData = {};
        curBook.formData.is_manual_condition = (normalized === 'Удовлетворительная');
      }
    } else {
      // Фото дефектов НЕТ
      if (isUserManual) {
        if (normalized === 'Хорошая' || normalized === 'Удовлетворительная') {
          if (curBook) {
            if (!curBook.formData) curBook.formData = {};
            curBook.formData.is_manual_condition = true;
          }
          if (typeof window.showToast === 'function') {
            window.showToast(`💡 Установлена сохранность «${normalized}». Предупреждение добавлено в аннотацию.`);
          }
        } else if (normalized === 'Очень хорошая') {
          if (curBook && curBook.formData) {
            curBook.formData.is_manual_condition = false;
          }
        }
      } else {
        // Автоматический вызов при отсутствии фото дефектов:
        // Если пользователь ранее выбрал "Хорошая" или "Удовлетворительная", сохраняем её!
        if (curBook && curBook.formData && (curBook.formData.condition === 'Хорошая' || curBook.formData.condition === 'Удовлетворительная')) {
          normalized = curBook.formData.condition;
          curBook.formData.is_manual_condition = true;
        } else {
          normalized = 'Очень хорошая';
        }
      }
    }

    const condEl = document.getElementById('condition');
    if (condEl) condEl.value = normalized;
    if (curBook) {
      if (!curBook.formData) curBook.formData = {};
      curBook.formData.condition = normalized;
    }

    // Синхронизируем аннотацию с предупреждением:
    // Предупреждение добавляется, если есть дефекты ИЛИ состояние ухудшено вручную ("Хорошая" / "Удовлетворительная")
    const antEl = document.getElementById('annotation');
    if (antEl && typeof window.cleanAnnotationText === 'function') {
      const cleanAnt = window.cleanAnnotationText(curBook?.formData?.annotation || antEl.value || '');
      const warningStr = window.ANNOTATION_WARNING || 'ВНИМАНИЕ! КНИГА НЕ НОВАЯ. Имеются определённые нюансы (повреждения) см. дополнительные фото.';
      let newAnt = cleanAnt;
      if (hasDefects || normalized === 'Хорошая' || normalized === 'Удовлетворительная') {
        if (cleanAnt) {
          newAnt = warningStr + '\n\n' + cleanAnt;
        }
      }
      if (antEl.value !== newAnt) {
        antEl.value = newAnt;
      }
      if (curBook && curBook.formData) curBook.formData.annotation = newAnt;
    }

    document.querySelectorAll('#condBtns .cond-btn').forEach(btn => {
      const bVal = btn.getAttribute('data-val');
      if (bVal === normalized) {
        if (normalized === 'Очень хорошая') {
          btn.className = 'cond-btn py-1.5 rounded-xl border border-emerald-500 bg-emerald-950/40 text-emerald-300 text-xs font-semibold transition text-center shadow-xs';
        } else if (normalized === 'Хорошая') {
          btn.className = 'cond-btn py-1.5 rounded-xl border border-amber-500 bg-amber-950/40 text-amber-300 text-xs font-semibold transition text-center shadow-xs';
        } else {
          btn.className = 'cond-btn py-1.5 rounded-xl border border-rose-500 bg-rose-950/40 text-rose-300 text-xs font-semibold transition text-center shadow-xs';
        }
      } else {
        btn.className = 'cond-btn py-1.5 rounded-xl border border-slate-700 bg-slate-950 text-slate-300 text-xs font-semibold hover:border-slate-500 transition text-center';
      }
    });

    const hintEl = document.getElementById('annotationNoticeHint');
    if (hintEl) {
      if (hasDefects) {
        hintEl.className = 'text-xs text-amber-400 mt-1.5 font-medium flex items-center gap-1.5';
        hintEl.innerHTML = `<span>⚠️</span> <span>В слоте [5. Дефекты] фото (${defectCount} шт.). Предупреждение в аннотации, сохранность: <b>${normalized}</b>.</span>`;
      } else if (normalized === 'Хорошая' || normalized === 'Удовлетворительная') {
        hintEl.className = 'text-xs text-amber-400 mt-1.5 font-medium flex items-center gap-1.5';
        hintEl.innerHTML = `<span>💡</span> <span>Сохранность вручную: <b>${normalized}</b>. Предупреждение добавлено в аннотацию.</span>`;
      } else {
        hintEl.className = 'text-xs text-emerald-400 mt-1.5 font-medium flex items-center gap-1.5';
        hintEl.innerHTML = `<span>✓</span> <span>Сохранность: <b>Очень хорошее</b>. Предупреждение отключено.</span>`;
      }
    }

    if (typeof window.saveCurrentFormToActiveBook === 'function') window.saveCurrentFormToActiveBook();
    if (typeof window.scheduleAutoSave === 'function') window.scheduleAutoSave();
  }

  // -------------------------------------------------------------
  // ГАБАРИТЫ И УПАКОВКА
  // -------------------------------------------------------------
  function onDimensionChange() {
    const isPkgAdder = document.getElementById('autoPackageAdder')?.checked !== false;

    const wEl = document.getElementById('width');
    const lEl = document.getElementById('length');
    const hEl = document.getElementById('height');
    const wtEl = document.getElementById('weight');

    const rawW = (wEl && parseInt(wEl.value, 10)) || 130;
    const rawL = (lEl && parseInt(lEl.value, 10)) || 205;
    const rawH = (hEl && parseInt(hEl.value, 10)) || 22;
    const rawWt = (wtEl && parseInt(wtEl.value, 10)) || 300;

    const pkg = window.BookCalculators
      ? window.BookCalculators.calcPackageDimensions(rawW, rawL, rawH, rawWt, isPkgAdder)
      : {
          width: isPkgAdder ? (rawW + 10) : rawW,
          length: isPkgAdder ? (rawL + 10) : rawL,
          height: isPkgAdder ? (rawH + 10) : rawH,
          weight: isPkgAdder ? (rawWt + 30) : rawWt,
          dimensions: `${isPkgAdder ? (rawW + 10) : rawW}х${isPkgAdder ? (rawL + 10) : rawL}х${isPkgAdder ? (rawH + 10) : rawH}`,
        };

    const dimStr = pkg.dimensions;
    const dimEl = document.getElementById('dimensions');
    if (dimEl) dimEl.value = dimStr;

    if (document.getElementById('width_package')) document.getElementById('width_package').value = pkg.width;
    if (document.getElementById('length_package')) document.getElementById('length_package').value = pkg.length;
    if (document.getElementById('height_package')) document.getElementById('height_package').value = pkg.height;
    if (document.getElementById('weight_package')) document.getElementById('weight_package').value = pkg.weight;

    const wHint = document.getElementById('pkgWidthHint');
    const lHint = document.getElementById('pkgLengthHint');
    const hHint = document.getElementById('pkgHeightHint');
    const wtHint = document.getElementById('pkgWeightHint');
    if (wHint) wHint.textContent = isPkgAdder ? `упак: ${pkg.width} мм (+10)` : `упак: ${pkg.width} мм`;
    if (lHint) lHint.textContent = isPkgAdder ? `упак: ${pkg.length} мм (+10)` : `упак: ${pkg.length} мм`;
    if (hHint) hHint.textContent = isPkgAdder ? `упак: ${pkg.height} мм (+10)` : `упак: ${pkg.height} мм`;
    if (wtHint) wtHint.textContent = isPkgAdder ? `упак: ${pkg.weight} г (+30)` : `упак: ${pkg.weight} г`;

    const badge = document.getElementById('dimensionsPreviewBadge');
    if (badge) {
      badge.textContent = `В Ozon: ${pkg.width} × ${pkg.length} × ${pkg.height} мм · ${pkg.weight} г`;
    }

    if (typeof window.saveCurrentFormToActiveBook === 'function') window.saveCurrentFormToActiveBook();
    if (typeof window.scheduleAutoSave === 'function') window.scheduleAutoSave();
  }

  function setBookFormat(w, l) {
    const wEl = document.getElementById('width');
    const lEl = document.getElementById('length');
    if (wEl) wEl.value = w;
    if (lEl) lEl.value = l;
    autoCalcDimensions(true);
    if (typeof window.updateCardModeBanner === 'function') {
      window.updateCardModeBanner();
    }
  }

  function updateDimensionsPreviewBadge() {
    onDimensionChange();
  }

  function autoCalcDimensions(force = false) {
    const pages = parseInt(document.getElementById('pages')?.value, 10) || 200;
    const widthEl = document.getElementById('width');
    const lengthEl = document.getElementById('length');
    const heightEl = document.getElementById('height');
    const weightEl = document.getElementById('weight');

    let w = (widthEl && parseInt(widthEl.value, 10)) || 130;
    let l = (lengthEl && parseInt(lengthEl.value, 10)) || 205;

    const coverVal = document.getElementById('cover_type')?.value || 'Твердый переплет';
    const paperVal = document.getElementById('paper_type')?.value || 'Офсетная';

    const calculated = window.BookCalculators
      ? window.BookCalculators.calculateDimensionsAndWeight({ pages, coverType: coverVal, paperType: paperVal, width: w, length: l })
      : { width: w, length: l, height: 22, weight: 300 };

    if (widthEl && (force || !widthEl.value || widthEl.value === '0')) widthEl.value = calculated.width;
    if (lengthEl && (force || !lengthEl.value || lengthEl.value === '0')) lengthEl.value = calculated.length;
    if (heightEl && (force || !heightEl.value || heightEl.value === '0')) heightEl.value = calculated.height;
    if (weightEl && (force || !weightEl.value || weightEl.value === '0')) weightEl.value = calculated.weight;

    onDimensionChange();
  }

  function syncDimensions() {
    onDimensionChange();
  }

  function autoDetectCountry() {
    const year = parseInt(document.getElementById('year')?.value, 10) || 0;
    const countryEl = document.getElementById('country');
    if (countryEl) {
      if (year > 0 && year < 1992) {
        countryEl.value = 'СССР';
      } else if (year >= 1992) {
        countryEl.value = 'Россия';
      }
    }
  }

  function handleGenreChange() {
    const ta = document.getElementById('target_audience');
    if (ta) ta.value = '';
  }

  async function generateNewArticle() {
    const numEl = document.getElementById('article_number');
    const curVal = numEl ? numEl.value.replace(/\D/g, '') : '';
    let nextArt = '';

    if (curVal) {
      // Пользователь уже работает в определенном диапазоне (например 03500).
      // Кнопка (+1) просто прибавляет 1 к текущему номеру!
      const curNum = parseInt(curVal, 10);
      const nextNum = curNum + 1;
      nextArt = `DP-B-${String(nextNum).padStart(5, '0')}`;
    } else {
      // Если поле пустое, берем следующий свободный
      nextArt = (typeof window.calculateNextArticle === 'function')
        ? await window.calculateNextArticle(1)
        : 'DP-B-03098';
    }

    const artEl = document.getElementById('article');
    if (artEl) artEl.value = nextArt;
    if (typeof window.onArticleInput === 'function') {
      window.onArticleInput(nextArt);
    } else if (numEl) {
      numEl.value = nextArt.replace(/\D/g, '').slice(-5);
    }
  }

  function generateArticleByAuthor() {
    const author = document.getElementById('author')?.value?.trim() || document.getElementById('author_cover')?.value?.trim();
    const year = document.getElementById('year')?.value?.trim();
    if (!author) {
      alert('Сначала укажите автора или распознайте книгу через ИИ!');
      return;
    }
    const words = author.replace(/[^A-Za-zА-Яа-я0-9\s]/g, '').trim().split(/\s+/);
    const surname = (words[0] || 'BOOK').toUpperCase();
    const suffix = year ? `-${year}` : `-${String(window.activeBookId).padStart(2, '0')}`;
    const art = `${surname}${suffix}`;
    const artEl = document.getElementById('article');
    if (artEl) artEl.value = art;
    if (typeof window.onArticleInput === 'function') window.onArticleInput(art);
  }

  function deriveBarcodeFromIsbn() {
    const isbn = document.getElementById('isbn')?.value?.trim() || '';
    const res = window.BookCalculators
      ? window.BookCalculators.deriveBarcodeFromIsbn(isbn)
      : { success: false, error: 'Калькулятор штрихкодов не инициализирован' };

    if (!res.success) {
      alert(res.error || `В поле ISBN должно быть 10 или 13 цифр (например: 978-5-17-147716-5)! Сейчас там: "${isbn}"`);
      return;
    }

    const finalBarcode = res.barcode;
    const bcEl = document.getElementById('barcode');
    if (bcEl) {
      bcEl.value = finalBarcode;
      bcEl.classList.add('field-updated');
      setTimeout(() => bcEl.classList.remove('field-updated'), 1000);
    }
    if (typeof window.onBarcodeInput === 'function') window.onBarcodeInput(finalBarcode);
    if (typeof window.showToast === 'function') window.showToast(`Штрихкод установлен из ISBN: <b>${finalBarcode}</b>`);
  }

  async function clearForm(customArt = null) {
    const book = typeof window.getActiveBook === 'function' ? window.getActiveBook() : null;
    if (book && (book.isEditMode || book.isReopened) && !customArt) {
      if (typeof window.cancelEditModeAndCreateNew === 'function') {
        return await window.cancelEditModeAndCreateNew();
      }
    }

    if (window.BookForm && window.BookForm.initialized) {
      window.BookForm.clearForm({
        brand: 'Нет бренда',
        auto_package_adder: true,
        isbn: (window.currentTemplateMode === 'pre2011') ? '' : '978-5-0000-0000-0',
        country: 'Россия',
        cover_type: 'Твердый переплет',
        paper_type: '',
        genre: 'Проза',
        age_limit: '',
        target_audience: '',
        hashtags: '',
        condition: 'Очень хорошая'
      });
    } else {
      ['title', 'original_title', 'author_cover', 'author', 'series', 'illustrator', 'translator', 'publisher', 'year', 'pages', 'price', 'old_price'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
      });
      const antEl = document.getElementById('annotation');
      if (antEl) antEl.value = '';
      const brandEl = document.getElementById('brand');
      if (brandEl) brandEl.value = 'Нет бренда';
      if (document.getElementById('autoPackageAdder')) {
        document.getElementById('autoPackageAdder').checked = true;
      }
      const isbnEl = document.getElementById('isbn');
      if (isbnEl) {
        isbnEl.value = (window.currentTemplateMode === 'pre2011') ? '' : '978-5-0000-0000-0';
      }
      if (document.getElementById('country')) document.getElementById('country').value = 'Россия';
      if (document.getElementById('cover_type')) document.getElementById('cover_type').value = 'Твердый переплет';
      if (document.getElementById('paper_type')) document.getElementById('paper_type').value = '';
      if (document.getElementById('genre')) document.getElementById('genre').value = 'Проза';
      if (document.getElementById('age_limit')) document.getElementById('age_limit').value = '';
      if (document.getElementById('target_audience')) document.getElementById('target_audience').value = '';
      if (document.getElementById('hashtags')) document.getElementById('hashtags').value = '';
    }
    if (typeof window.syncAnnotationWarningWithDefectsSlot === 'function') {
      window.syncAnnotationWarningWithDefectsSlot();
    }

    let art = customArt;
    if (!art && book && (book.article || (book.formData && book.formData.article))) {
      art = (book.formData && book.formData.article) || book.article;
    }
    if (!art) {
      const idx = (window.booksSession || []).indexOf(book);
      art = (typeof window.calculateNextArticle === 'function')
        ? await window.calculateNextArticle(idx >= 0 ? idx : 0)
        : 'DP-B-00001';
    }
    const fullArt = (typeof window.syncArticleInputs === 'function') ? window.syncArticleInputs(art) : art;
    const bc = window.BookCalculators
      ? window.BookCalculators.generateEan13FromArticle(fullArt)
      : (window.generateEan13FromArticle ? window.generateEan13FromArticle(fullArt) : '2978470000012');

    const bcEl = document.getElementById('barcode');
    if (bcEl) bcEl.value = bc;
    if (book) {
      book.article = fullArt;
      if (!book.formData) book.formData = {};
      book.formData.article = fullArt;
      book.formData.article_number = fullArt.replace(/\D/g, '').slice(-5);
      book.formData.barcode = bc;
      book.formData.template_mode = window.currentTemplateMode;
      book.formData.auto_package_adder = true;
    }
    autoCalcDimensions();
    if (typeof window.updateCardModeBanner === 'function') {
      window.updateCardModeBanner();
    }
  }

  // -------------------------------------------------------------
  // ОРКЕСТРАЦИЯ СОХРАНЕНИЯ В EXCEL И VAULT
  // -------------------------------------------------------------
  async function handlePrimaryBookSave() {
    return await saveBookToExcel();
  }

  async function saveBookToExcel() {
    if (typeof window.snapToCanonical === 'function') {
      window.snapToCanonical(document.getElementById('author_cover'), 'authors');
      window.snapToCanonical(document.getElementById('author'), 'authors');
      window.snapToCanonical(document.getElementById('publisher'), 'publishers');
      window.snapToCanonical(document.getElementById('brand'), 'brands');
      window.snapToCanonical(document.getElementById('series'), 'series');
      window.snapToCanonical(document.getElementById('translator'), 'translators');
      window.snapToCanonical(document.getElementById('illustrator'), 'illustrators');
    }

    const title = document.getElementById('title')?.value?.trim();
    if (!title) {
      alert('Пожалуйста, укажите название книги!');
      document.getElementById('title')?.focus();
      return;
    }

    let authorCover = document.getElementById('author_cover')?.value?.trim();
    if (!authorCover) {
      alert('Пожалуйста, укажите автора на обложке (если автор отсутствует в книге, введите «не указан»)!');
      document.getElementById('author_cover')?.focus();
      return;
    }
    if (['автор не указан', 'нет автора', 'неизвестен', 'нет', 'отсутствует'].includes(authorCover.toLowerCase())) {
      authorCover = 'не указан';
      if (document.getElementById('author_cover')) document.getElementById('author_cover').value = 'не указан';
    }

    let author = document.getElementById('author')?.value?.trim();
    if (!author) {
      alert('Пожалуйста, укажите официального автора книги (в паспортном формате «Фамилия Имя Отчество», либо «не указан»)!');
      document.getElementById('author')?.focus();
      return;
    }
    if (['автор не указан', 'нет автора', 'неизвестен', 'нет', 'отсутствует'].includes(author.toLowerCase())) {
      author = 'не указан';
      if (document.getElementById('author')) document.getElementById('author').value = 'не указан';
    }

    const paperType = document.getElementById('paper_type')?.value?.trim();
    if (!paperType) {
      alert('Пожалуйста, выберите тип бумаги перед сохранением карточки!');
      document.getElementById('paper_type')?.focus();
      return;
    }

    const priceRaw = document.getElementById('price')?.value?.trim() || '';
    const priceVal = parseInt(priceRaw, 10);
    if (!priceVal || priceVal <= 0 || isNaN(priceVal)) {
      alert('Пожалуйста, укажите цену продажи книги (должна быть больше 0)!');
      document.getElementById('price')?.focus();
      return;
    }

    let article = document.getElementById('article')?.value?.trim();
    if (!article) {
      await generateNewArticle();
      article = document.getElementById('article')?.value?.trim() || 'DP-B-00001';
    }

    const book = typeof window.getActiveBook === 'function' ? window.getActiveBook() : null;
    const isEdit = Boolean(book && (book.isEditMode || book.isReopened || book.isSavedToExcel));

    // Проверка уникальности артикула перед созданием новой книги
    if (!isEdit) {
      try {
        const checkRes = await fetch(`/api/check_article?article=${encodeURIComponent(article)}`).then(r => r.json());
        if (checkRes && checkRes.exists) {
          const sug = checkRes.suggested_next_article || 'DP-B-03098';
          const conf = confirm(
            `⚠️ Внимание! Товар с артикулом ${article} уже существует («${checkRes.title || 'Товар на Ozon'}»).\n\n` +
            `Перезапись старых карточек заблокирована для защиты данных.\n\n` +
            `• Нажмите «ОК», чтобы создать новую книгу под свободным артикулом ${sug}.\n` +
            `• Нажмите «Отмена», если вы хотели отредактировать этот товар (нажмите «📥 Загрузить»).`
          );
          if (conf) {
            article = sug;
            if (typeof window.onArticleInput === 'function') window.onArticleInput(sug);
          } else {
            return;
          }
        }
      } catch (chkErr) {
        console.warn('Pre-save check failed:', chkErr);
      }
    }

    let barcodeVal = document.getElementById('barcode')?.value?.trim();
    if (!barcodeVal || barcodeVal === 'генерирует озон' || !/^\d{12,13}$/.test(barcodeVal)) {
      barcodeVal = window.BookCalculators
        ? window.BookCalculators.generateEan13FromArticle(article)
        : (window.generateEan13FromArticle ? window.generateEan13FromArticle(article) : '2978470000012');
      if (document.getElementById('barcode')) document.getElementById('barcode').value = barcodeVal;
    }

    const btn = document.getElementById('saveBtn');
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span>⏳</span> <span>Публикация в Ozon, Vault и Excel...</span>';
    }

    const isbnVal = document.getElementById('isbn')?.value?.trim() || '';
    let publisherVal = document.getElementById('publisher')?.value?.trim() || '';
    if (typeof window.cleanPublisherName === 'function') {
      publisherVal = window.cleanPublisherName(publisherVal);
      if (document.getElementById('publisher')) document.getElementById('publisher').value = publisherVal;
    }

    const isPkgAdder = document.getElementById('autoPackageAdder')?.checked !== false;
    const rawWidth = parseInt(document.getElementById('width')?.value, 10) || 130;
    const rawLength = parseInt(document.getElementById('length')?.value, 10) || 205;
    const rawHeight = parseInt(document.getElementById('height')?.value, 10) || 22;
    const rawWeight = parseInt(document.getElementById('weight')?.value, 10) || 300;

    const pkgDims = window.BookCalculators
      ? window.BookCalculators.calcPackageDimensions(rawWidth, rawLength, rawHeight, rawWeight, isPkgAdder)
      : { width: isPkgAdder ? rawWidth + 10 : rawWidth, length: isPkgAdder ? rawLength + 10 : rawLength, height: isPkgAdder ? rawHeight + 10 : rawHeight, weight: isPkgAdder ? rawWeight + 30 : rawWeight, dimensions: `${rawWidth}х${rawLength}х${rawHeight}` };

    const pkgWidth = pkgDims.width;
    const pkgLength = pkgDims.length;
    const pkgHeight = pkgDims.height;
    const pkgWeight = pkgDims.weight;
    const dimStr = pkgDims.dimensions;

    const rawYearVal = document.getElementById('year')?.value?.trim() || '';
    const yInt = parseInt(rawYearVal, 10);
    const resolvedTemplateMode = window.BookValidators
      ? window.BookValidators.resolveTemplateMode(yInt)
      : ((!isNaN(yInt) && yInt > 1000 && yInt < 2100) ? (yInt <= 2011 ? 'pre2011' : 'post2011') : (window.currentTemplateMode || 'pre2011'));
    if (resolvedTemplateMode !== window.currentTemplateMode && typeof setTemplateMode === 'function') {
      try { setTemplateMode(resolvedTemplateMode, false); } catch (e) {}
    }

    const formData = (window.BookForm && window.BookForm.initialized) ? window.BookForm.readForm() : {};
    const payload = {
      template_mode: resolvedTemplateMode,
      article: article,
      is_edit: isEdit,
      isReopened: Boolean(book && (book.isReopened || book.isSavedToExcel || book.isEditMode)),
      barcode: barcodeVal,
      isbn: (resolvedTemplateMode === 'pre2011') ? isbnVal : (isbnVal || '978-5-0000-0000-0'),
      title: title,
      original_title: String(formData.original_title !== undefined ? formData.original_title : (document.getElementById('original_title')?.value || '')).trim(),
      series: String(formData.series !== undefined ? formData.series : (document.getElementById('series')?.value || '')).trim(),
      author_cover: authorCover,
      author: author,
      illustrator: String(formData.illustrator !== undefined ? formData.illustrator : (document.getElementById('illustrator')?.value || '')).trim(),
      translator: String(formData.translator !== undefined ? formData.translator : (document.getElementById('translator')?.value || '')).trim(),
      publisher: publisherVal,
      brand: String(formData.brand !== undefined ? formData.brand : (document.getElementById('brand')?.value || '')).trim() || 'Нет бренда',
      year: String(formData.year !== undefined ? formData.year : (document.getElementById('year')?.value || '')).trim(),
      pages: String(formData.pages !== undefined ? formData.pages : (document.getElementById('pages')?.value || '')).trim(),
      country: formData.country || document.getElementById('country')?.value || 'Россия',
      cover_type: formData.cover_type || document.getElementById('cover_type')?.value || 'Твердый переплет',
      paper_type: paperType,
      genre: formData.genre || document.getElementById('genre')?.value || 'Проза',
      age_limit: formData.age_limit || document.getElementById('age_limit')?.value || '',
      target_audience: '',
      condition: formData.condition || document.getElementById('condition')?.value || 'Очень хорошая',
      defects: '',
      annotation: String(formData.annotation !== undefined ? formData.annotation : (document.getElementById('annotation')?.value || '')).trim(),
      hashtags: '',
      price: String(priceVal),
      old_price: String(formData.old_price !== undefined ? formData.old_price : (document.getElementById('old_price')?.value || '')).trim(),
      dimensions: dimStr,
      weight: rawWeight,
      width: rawWidth,
      length: rawLength,
      height: rawHeight,
      weight_g: rawWeight,
      width_mm: rawWidth,
      length_mm: rawLength,
      height_mm: rawHeight,
      width_package: pkgWidth,
      length_package: pkgLength,
      height_package: pkgHeight,
      weight_package: pkgWeight,
      auto_package_adder: isPkgAdder,
      collect_reviews: 'Нет',
    };

    const extractPhotoPayload = (p) => {
      if (!p) return null;
      let d = p.data || p.preview || p.croppedBase || p.cameraOriginal || '';
      if (typeof d === 'string' && d.startsWith('data:') && d.includes(',')) {
        d = d.split(',')[1];
      }
      return {
        id: p.id,
        data: d,
        preview: p.preview || null,
        croppedBase: p.croppedBase || null,
        cameraOriginal: p.cameraOriginal || null,
        name: p.name || 'photo.jpg',
        s3_url: p.s3_url || null,
        is_s3_uploaded: Boolean(p.is_s3_uploaded),
      };
    };

    const cbPayload = book ? (Array.isArray(book.slots.cover_back)
      ? book.slots.cover_back.map(extractPhotoPayload).filter(Boolean)
      : (book.slots.cover_back ? [extractPhotoPayload(book.slots.cover_back)].filter(Boolean) : [])) : [];

    const slots_photos = {
      cover_front: book ? extractPhotoPayload(book.slots.cover_front) : null,
      cover_back: cbPayload,
      info_pages: book ? (book.slots.info_pages || []).map(extractPhotoPayload).filter(Boolean) : [],
      illustrations: book ? (book.slots.illustrations || []).map(extractPhotoPayload).filter(Boolean) : [],
      mantra_defects: book ? (book.slots.mantra_defects || []).map(extractPhotoPayload).filter(Boolean) : []
    };
    payload.slots_photos = slots_photos;

    const hasMantraDefects = Boolean(book && book.slots.mantra_defects && book.slots.mantra_defects.length > 0);
    payload.has_mantra_defects = hasMantraDefects;

    let finalAnt = typeof window.cleanAnnotationText === 'function'
      ? window.cleanAnnotationText(document.getElementById('annotation')?.value || '')
      : (document.getElementById('annotation')?.value || '');
    if (hasMantraDefects && finalAnt) {
      finalAnt = (window.ANNOTATION_WARNING || 'ВНИМАНИЕ! КНИГА НЕ НОВАЯ. Имеются определённые нюансы (повреждения) см. дополнительные фото.') + '\n\n' + finalAnt;
    }
    payload.annotation = finalAnt;

    try {
      const result = window.ApiClient
        ? await window.ApiClient.saveBook(payload)
        : await fetch('/api/save_book', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          }).then(r => r.json());

      if (result.success) {
        if (window.EventBus) window.EventBus.emit('book:saved', result);
        if (typeof window.updateBooksCount === 'function') window.updateBooksCount();
        if (typeof window.refreshPreviewTable === 'function') {
          window.refreshPreviewTable(result.template_mode || window.currentTemplateMode);
        }
        const photoCount = (result.saved_photos && result.saved_photos.length) || 0;
        const s3Badge = result.s3_enabled ? ' ☁️ [Yandex S3]' : '';
        const ozonBadge = (result.ozon_info && result.ozon_info.published)
          ? ` 🚀 [Ozon #${result.ozon_info.task_id || 'OK'}]`
          : '';
        const photoMsg = photoCount > 0 ? ` (в архив и S3 сохранено ${photoCount} фото${s3Badge}${ozonBadge})` : '';
        const today = typeof window.getTodayStr === 'function' ? window.getTodayStr() : '';
        const fileName = result.file_name || ((result.template_mode === 'pre2011') ? `${today}_Печатная книга_до_2011.xlsx` : `${today}_Печатная книга_после_2011.xlsx`);
        const targetFolder = result.folder || ((result.template_mode === 'pre2011') ? 'ready_tables/1942-2010' : 'ready_tables/с_2011');
        const status = document.getElementById('formStatus');
        if (status) {
          status.textContent = `✅ Книга "${result.title}" записана в ${targetFolder}/${fileName}!${photoMsg}`;
          status.className = 'text-center text-xs text-emerald-400 font-semibold';
        }
        if (typeof window.showToast === 'function') {
          window.showToast(`✅ Записано в <b>${targetFolder}/${fileName}</b> (строка ${result.row})${s3Badge}${ozonBadge}`);
        }

        // Асинхронная проверка статуса модерации Ozon без блокировки оператора
        if (result.ozon_info && result.ozon_info.task_id) {
          const taskId = result.ozon_info.task_id;
          setTimeout(async () => {
            try {
              const taskRes = window.ApiClient
                ? await window.ApiClient.getOzonTaskStatus(taskId)
                : await fetch(`/api/ozon/task_status?task_id=${taskId}`).then(r => r.json());
              if (taskRes && taskRes.success && taskRes.result) {
                const items = taskRes.result.items || [];
                const hasErrors = items.some(it => it.errors && it.errors.length > 0);
                if (hasErrors) {
                  const errList = items.flatMap(it => (it.errors || []).map(e => e.message || e.error || e)).join('; ');
                  if (typeof window.showToast === 'function') {
                    window.showToast(`⚠️ Ozon модерация: ${errList}`);
                  }
                } else if (items.length > 0) {
                  if (typeof window.showToast === 'function') {
                    window.showToast(`✅ Ozon: Товар ${result.article} успешно подтвержден модерацией!`);
                  }
                }
              }
            } catch (ePoll) {
              console.warn('Ozon task poll error:', ePoll);
            }
          }, 3500);
        }

        if (book) {
          book.isSavedToExcel = true;
          book.isEditMode = true;
          if (result.slots) {
            book.slots = result.slots;
            // Фото сохраняются в слотах книги; в общем photoPool только обновляем привязку, если фото было загружено из пула
            Object.entries(result.slots).forEach(([slotKey, slotItem]) => {
              const items = Array.isArray(slotItem) ? slotItem : (slotItem ? [slotItem] : []);
              items.forEach(p => {
                if (p && p.id && window.photoPool) {
                  p.assignedBookId = book.id;
                  p.assignedSlot = slotKey;
                  const existingIdx = window.photoPool.findIndex(x => x.id === p.id);
                  if (existingIdx >= 0) {
                    window.photoPool[existingIdx] = { ...window.photoPool[existingIdx], ...p, assignedBookId: book.id, assignedSlot: slotKey };
                  }
                }
              });
            });
          }
        }
        if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
        if (typeof window.renderPool === 'function') window.renderPool();
        if (typeof window.loadCatalogReferences === 'function') window.loadCatalogReferences();
        if (typeof window.renderBooksTabs === 'function') window.renderBooksTabs();
        if (typeof window.updateCardModeBanner === 'function') window.updateCardModeBanner();
        if (typeof window.scheduleAutoSave === 'function') window.scheduleAutoSave();

        // Предлагаем перейти к следующей книге если есть неразобранные фото
        const unassigned = (window.photoPool || []).filter(p => !p.assignedBookId && !(window.isPhotoInAnyBookSlot && window.isPhotoInAnyBookSlot(p.id))).length;
        if (unassigned > 0) {
          const templateLabel = (result.template_mode === 'pre2011') ? 'До 2011 г.' : 'После 2011 г.';
          setTimeout(() => {
            if (confirm(`Книга сохранена в шаблон (${templateLabel})! В пуле осталось ${unassigned} неразобранных фото. Создать карточку следующей книги?`)) {
              if (typeof window.addNewBook === 'function') window.addNewBook();
            }
          }, 600);
        }
      } else {
        if (result.code === 'ARTICLE_ALREADY_EXISTS') {
          const sug = result.suggested_article;
          const conf = confirm(
            `⚠️ Ошибка: ${result.error}\n\n` +
            `Подставить свободный артикул ${sug} и попробовать снова?`
          );
          if (conf && sug) {
            if (typeof window.onArticleInput === 'function') window.onArticleInput(sug);
          }
        } else {
          alert('Ошибка записи: ' + (result.error || 'Неизвестная ошибка'));
        }
      }
    } catch (err) {
      alert('Ошибка записи: ' + err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
      }
      try {
        if (typeof window.updateCardModeBanner === 'function') {
          window.updateCardModeBanner();
        }
      } catch (eBanner) {
        console.error('updateCardModeBanner error in finally:', eBanner);
      }
      if (btn && btn.innerHTML.includes('⏳')) {
        const curBook = typeof window.getActiveBook === 'function' ? window.getActiveBook() : null;
        const curArt = (curBook && (curBook.article || (curBook.formData && curBook.formData.article))) || document.getElementById('article')?.value || '';
        if (curBook && (curBook.isSavedToExcel || curBook.isEditMode || curBook.isReopened)) {
          btn.innerHTML = `<span id="saveBtnIcon">💾</span> <span id="saveBtnText">Сохранить изменения книги ${curArt} в Excel, Ozon и БД (Cmd + Enter)</span>`;
        } else {
          btn.innerHTML = '<span id="saveBtnIcon">✨</span> <span id="saveBtnText">Записать новую книгу в таблицу Ozon (Cmd + Enter)</span>';
        }
      }
    }
  }

  // -------------------------------------------------------------
  // ГОРЯЧИЕ КЛАВИШИ (KEYBOARD SHORTCUTS)
  // -------------------------------------------------------------
  window.addEventListener('keydown', (e) => {
    const activeTag = (document.activeElement?.tagName || '').toLowerCase();
    const isInputFocused = ['input', 'textarea', 'select'].includes(activeTag);

    if (window.isStudioOpen) {
      if (e.key === 'Escape') {
        if (typeof window.closePhotoStudio === 'function') window.closePhotoStudio(false);
        e.preventDefault();
        return;
      }

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault();
        if (typeof window.saveStudioChanges === 'function') window.saveStudioChanges();
        return;
      }

      if ((e.metaKey || e.ctrlKey) && ((e.shiftKey && e.key.toLowerCase() === 'z') || e.key.toLowerCase() === 'y')) {
        e.preventDefault();
        if (typeof window.redoStudioAction === 'function') window.redoStudioAction();
        return;
      }

      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        if (typeof window.undoStudioAction === 'function') window.undoStudioAction();
        return;
      }

      if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        if (typeof window.saveStudioChanges === 'function') window.saveStudioChanges();
        return;
      }

      if (!isInputFocused || document.activeElement?.type === 'range') {
        if (e.key === 'ArrowRight' || e.key === ']') {
          e.preventDefault();
          if (typeof window.navigateStudioPhoto === 'function') window.navigateStudioPhoto(1);
          return;
        }
        if (e.key === 'ArrowLeft' || e.key === '[') {
          e.preventDefault();
          if (typeof window.navigateStudioPhoto === 'function') window.navigateStudioPhoto(-1);
          return;
        }
        if (e.key.toLowerCase() === 'r') {
          e.preventDefault();
          if (typeof window.rotateStudio === 'function') window.rotateStudio(e.shiftKey ? -90 : 90);
          return;
        }
        if (e.key.toLowerCase() === 'c') {
          e.preventDefault();
          if (typeof window.toggleStudioCropMode === 'function') window.toggleStudioCropMode();
          return;
        }
        if (e.key.toLowerCase() === 'm' || e.key.toLowerCase() === 'v') {
          e.preventDefault();
          if (typeof window.setStudioInteractionMode === 'function') window.setStudioInteractionMode('move');
          if (typeof window.showToast === 'function') window.showToast('✋ Режим перемещения кадра');
          return;
        }
        if (e.key.toLowerCase() === 'w') {
          e.preventDefault();
          if (typeof window.applyStudioPreset === 'function') window.applyStudioPreset('clean_white');
          if (typeof window.showToast === 'function') window.showToast('✨ Применен пресет: Студия Ozon (белый фон)');
          return;
        }
        if (e.key.toLowerCase() === 't') {
          e.preventDefault();
          if (typeof window.applyStudioPreset === 'function') window.applyStudioPreset('sharp_text');
          if (typeof window.showToast === 'function') window.showToast('📝 Применен пресет: Четкий текст');
          return;
        }
        if (e.key === '0' || e.key.toLowerCase() === 'o') {
          e.preventDefault();
          if (typeof window.applyStudioPreset === 'function') window.applyStudioPreset('original');
          if (typeof window.showToast === 'function') window.showToast('⚪ Фильтры сброшены в оригинал');
          return;
        }
        if (e.key === '+' || e.key === '=') {
          e.preventDefault();
          if (typeof window.zoomStudio === 'function') window.zoomStudio(0.15);
          return;
        }
        if (e.key === '-' || e.key === '_') {
          e.preventDefault();
          if (typeof window.zoomStudio === 'function') window.zoomStudio(-0.15);
          return;
        }
      }
      return;
    }

    if (e.key === 'Escape') {
      if (typeof window.closeNewSessionModal === 'function') window.closeNewSessionModal();
      if (typeof window.closePhotoStudio === 'function') window.closePhotoStudio(false);
      if (typeof window.closeQrModal === 'function') window.closeQrModal();
      if (typeof window.closeKeyModal === 'function') window.closeKeyModal();
      if (typeof window.closeCardModal === 'function') window.closeCardModal();
      if (typeof window.closeClearTableModal === 'function') window.closeClearTableModal();
    }
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      handlePrimaryBookSave();
    }
  });

  // -------------------------------------------------------------
  // ИНИЦИАЛИЗАЦИЯ ПРИ ЗАГРУЗКЕ СТРАНИЦЫ
  // -------------------------------------------------------------
  window.addEventListener('DOMContentLoaded', async () => {
    setTemplateMode('pre2011', false);
    if (typeof window.loadSavedKey === 'function') window.loadSavedKey();
    if (typeof window.loadOzonStatus === 'function') window.loadOzonStatus();
    if (typeof window.updateBooksCount === 'function') window.updateBooksCount();
    if (typeof window.refreshPreviewTable === 'function') window.refreshPreviewTable('pre2011');
    if (typeof window.loadMobileUrl === 'function') window.loadMobileUrl();
    if (typeof window.loadCatalogReferences === 'function') window.loadCatalogReferences();
    if (typeof window.startMobileEventListener === 'function') window.startMobileEventListener();
    if (typeof window.initRotaryDial === 'function') window.initRotaryDial();

    const formContainer = document.getElementById('ozonFormContainer');
    if (formContainer && typeof window.scheduleAutoSave === 'function') {
      formContainer.addEventListener('input', window.scheduleAutoSave);
      formContainer.addEventListener('change', window.scheduleAutoSave);
    }

    const restored = (typeof window.restoreSessionDraft === 'function') ? await window.restoreSessionDraft() : false;
    if (!restored) {
      const initArt = (typeof window.calculateNextArticle === 'function') ? await window.calculateNextArticle(0) : 'DP-B-03098';
      if (window.booksSession && window.booksSession[0]) {
        window.booksSession[0].article = initArt;
        if (!window.booksSession[0].formData) window.booksSession[0].formData = {};
        window.booksSession[0].formData.article = initArt;
      }
      if (typeof window.renderBooksTabs === 'function') window.renderBooksTabs();
      if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
      clearForm(initArt);
      autoCalcDimensions();
    }
    if (typeof window.initBatchArticleInput === 'function') window.initBatchArticleInput();
    if (typeof window.updateCardModeBanner === 'function') window.updateCardModeBanner();
  });

  // Экспорт на window
  window.setTemplateMode = setTemplateMode;
  window.onYearInput = onYearInput;
  window.runManualEnrichment = runManualEnrichment;
  window.populateFields = populateFields;
  window.setPrice = setPrice;
  window.calcOldPrice = calcOldPrice;
  window.setCondition = setCondition;
  window.onDimensionChange = onDimensionChange;
  window.setBookFormat = setBookFormat;
  window.updateDimensionsPreviewBadge = updateDimensionsPreviewBadge;
  window.autoCalcDimensions = autoCalcDimensions;
  window.syncDimensions = syncDimensions;
  window.autoDetectCountry = autoDetectCountry;
  window.handleGenreChange = handleGenreChange;
  window.generateNewArticle = generateNewArticle;
  window.generateArticleByAuthor = generateArticleByAuthor;
  window.deriveBarcodeFromIsbn = deriveBarcodeFromIsbn;
  window.clearForm = clearForm;
  window.saveBookToExcel = saveBookToExcel;
  window.handlePrimaryBookSave = handlePrimaryBookSave;

})(window);
