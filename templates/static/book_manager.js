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

    if (window.currentTemplateMode === 'pre2011') {
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
      const targetMode = (y <= 2011) ? 'pre2011' : 'post2011';
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

      if (data.title) fill('title', data.title);
      if (data.original_title) fill('original_title', data.original_title);
      if (data.author_cover) fill('author_cover', data.author_cover);
      if (data.author || data.author_cover) fill('author', data.author || data.author_cover);
      if (data.publisher) fill('publisher', data.publisher);

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
        if (isCurrentActive) {
          try { onYearInput(data.year); } catch (e) { console.warn('onYearInput error', e); }
        }
      }

      // Правило: книги до 2011 года без 100% подтверждения на фото не требуют ISBN
      const isPre2011 = (recognizedYear > 0 && recognizedYear <= 2011) || window.currentTemplateMode === 'pre2011';
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
    const old = Math.round((p * 1.4) / 10) * 10;
    const oldPriceEl = document.getElementById('old_price');
    if (oldPriceEl) oldPriceEl.value = Math.max(old, p + 50);
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

    if (!hasDefects) {
      if (isUserManual && (normalized === 'Хорошая' || normalized === 'Удовлетворительная')) {
        if (typeof window.showToast === 'function') {
          window.showToast('💡 В слоте [5. Дефекты] нет фото — для книги всегда действует «Очень хорошее».');
        }
      }
      normalized = 'Очень хорошая';
    } else {
      if (normalized === 'Очень хорошая') {
        if (isUserManual && typeof window.showToast === 'function') {
          window.showToast('⚠️ В слоте [5. Дефекты] есть фото: сохранность не может быть «Очень хорошее».');
        }
        normalized = 'Хорошая';
      }
      if (!isUserManual && normalized === 'Удовлетворительная') {
        const prevSaved = curBook && curBook.formData && curBook.formData.condition;
        if (prevSaved !== 'Удовлетворительная') {
          normalized = 'Хорошая';
        }
      }
    }

    const condEl = document.getElementById('condition');
    if (condEl) condEl.value = normalized;
    if (curBook) {
      if (!curBook.formData) curBook.formData = {};
      curBook.formData.condition = normalized;
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

    const pkgW = isPkgAdder ? (rawW + 10) : rawW;
    const pkgL = isPkgAdder ? (rawL + 10) : rawL;
    const pkgH = isPkgAdder ? (rawH + 10) : rawH;
    const pkgWt = isPkgAdder ? (rawWt + 30) : rawWt;

    const dimStr = `${pkgW}х${pkgL}х${pkgH}`;
    const dimEl = document.getElementById('dimensions');
    if (dimEl) dimEl.value = dimStr;

    if (document.getElementById('width_package')) document.getElementById('width_package').value = pkgW;
    if (document.getElementById('length_package')) document.getElementById('length_package').value = pkgL;
    if (document.getElementById('height_package')) document.getElementById('height_package').value = pkgH;
    if (document.getElementById('weight_package')) document.getElementById('weight_package').value = pkgWt;

    const wHint = document.getElementById('pkgWidthHint');
    const lHint = document.getElementById('pkgLengthHint');
    const hHint = document.getElementById('pkgHeightHint');
    const wtHint = document.getElementById('pkgWeightHint');
    if (wHint) wHint.textContent = isPkgAdder ? `упак: ${pkgW} мм (+10)` : `упак: ${pkgW} мм`;
    if (lHint) lHint.textContent = isPkgAdder ? `упак: ${pkgL} мм (+10)` : `упак: ${pkgL} мм`;
    if (hHint) hHint.textContent = isPkgAdder ? `упак: ${pkgH} мм (+10)` : `упак: ${pkgH} мм`;
    if (wtHint) wtHint.textContent = isPkgAdder ? `упак: ${pkgWt} г (+30)` : `упак: ${pkgWt} г`;

    const badge = document.getElementById('dimensionsPreviewBadge');
    if (badge) {
      badge.textContent = `В Ozon: ${pkgW} × ${pkgL} × ${pkgH} мм · ${pkgWt} г`;
    }

    if (typeof window.saveCurrentFormToActiveBook === 'function') window.saveCurrentFormToActiveBook();
    if (typeof window.scheduleAutoSave === 'function') window.scheduleAutoSave();
  }

  function setBookFormat(w, l) {
    const wEl = document.getElementById('width');
    const lEl = document.getElementById('length');
    if (wEl) wEl.value = w;
    if (lEl) lEl.value = l;
    autoCalcDimensions();
  }

  function updateDimensionsPreviewBadge() {
    onDimensionChange();
  }

  function autoCalcDimensions() {
    const pages = parseInt(document.getElementById('pages')?.value, 10) || 200;
    const widthEl = document.getElementById('width');
    const lengthEl = document.getElementById('length');
    const heightEl = document.getElementById('height');
    const weightEl = document.getElementById('weight');

    let w = (widthEl && parseInt(widthEl.value, 10)) || 130;
    let l = (lengthEl && parseInt(lengthEl.value, 10)) || 205;
    if (w > l) { const tmp = w; w = l; l = tmp; }

    const coverVal = (document.getElementById('cover_type')?.value || 'Твердый переплет').toLowerCase();
    const isHard = coverVal.includes('тверд') || coverVal.includes('интегральн') || coverVal.includes('бумвинил') || coverVal.includes('кож') || coverVal.includes('тканев');

    const paperVal = (document.getElementById('paper_type')?.value || 'Офсетная').toLowerCase();
    let pDens = 80;
    if (paperVal.includes('мелован')) pDens = 115;
    else if (paperVal.includes('газетн')) pDens = 50;
    else if (paperVal.includes('типограф') || paperVal.includes('пухл')) pDens = 65;

    const areaM2 = (w / 1000.0) * (l / 1000.0);
    const sheets = pages / 2.0;
    const blockWt = sheets * areaM2 * pDens;

    let coverWt, spine;
    if (isHard) {
      coverWt = 2 * areaM2 * 1200 + 4 * areaM2 * 120 + 20;
      spine = Math.max(8, Math.round(pages * 0.048 + 3.5));
    } else {
      coverWt = 2 * areaM2 * 250 + 5;
      spine = Math.max(4, Math.round(pages * 0.048 + 1.0));
    }

    const bookWeight = Math.max(50, Math.round(blockWt + coverWt));

    if (widthEl && (!widthEl.value || widthEl.value === '0')) widthEl.value = w;
    if (lengthEl && (!lengthEl.value || lengthEl.value === '0')) lengthEl.value = l;
    if (heightEl) heightEl.value = spine;
    if (weightEl) weightEl.value = bookWeight;

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
    const book = typeof window.getActiveBook === 'function' ? window.getActiveBook() : null;
    const idx = (window.booksSession || []).indexOf(book);
    const nextArt = (typeof window.calculateNextArticle === 'function')
      ? await window.calculateNextArticle(idx >= 0 ? idx : 0)
      : 'DP-B-00001';
    const artEl = document.getElementById('article');
    if (artEl) artEl.value = nextArt;
    if (typeof window.onArticleInput === 'function') window.onArticleInput(nextArt);
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
    const digits = isbn.replace(/\D/g, '');
    let finalBarcode = '';
    if (digits.length === 13) {
      finalBarcode = digits;
    } else if (digits.length === 10) {
      const base12 = '978' + digits.substring(0, 9);
      const chk = window.BookCalculators ? window.BookCalculators.calcEan13Checksum(base12) : '0';
      finalBarcode = base12 + chk;
    } else {
      alert(`В поле ISBN должно быть 10 или 13 цифр (например: 978-5-17-147716-5)! Сейчас там: "${isbn}"`);
      return;
    }

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
    ['title', 'original_title', 'author_cover', 'author', 'series', 'illustrator', 'translator', 'publisher', 'year', 'pages', 'price', 'old_price'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.value = '';
    });
    const antEl = document.getElementById('annotation');
    if (antEl) antEl.value = '';
    if (typeof window.syncAnnotationWarningWithDefectsSlot === 'function') {
      window.syncAnnotationWarningWithDefectsSlot();
    }
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

    const book = typeof window.getActiveBook === 'function' ? window.getActiveBook() : null;
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
  }

  // -------------------------------------------------------------
  // ОРКЕСТРАЦИЯ СОХРАНЕНИЯ В EXCEL И VAULT
  // -------------------------------------------------------------
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

    const authorCover = document.getElementById('author_cover')?.value?.trim();
    if (!authorCover) {
      alert('Пожалуйста, укажите автора на обложке (если автор отсутствует в книге, введите «не указан»)!');
      document.getElementById('author_cover')?.focus();
      return;
    }

    const author = document.getElementById('author')?.value?.trim();
    if (!author) {
      alert('Пожалуйста, укажите официального автора книги (в паспортном формате «Фамилия Имя Отчество», либо «не указан»)!');
      document.getElementById('author')?.focus();
      return;
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
      btn.innerHTML = '<span>⏳</span> <span>Запись в таблицу Ozon...</span>';
    }

    const isbnVal = document.getElementById('isbn')?.value?.trim() || '';
    const publisherVal = document.getElementById('publisher')?.value?.trim() || '';

    const isPkgAdder = document.getElementById('autoPackageAdder')?.checked !== false;
    const rawWidth = parseInt(document.getElementById('width')?.value, 10) || 130;
    const rawLength = parseInt(document.getElementById('length')?.value, 10) || 205;
    const rawHeight = parseInt(document.getElementById('height')?.value, 10) || 22;
    const rawWeight = parseInt(document.getElementById('weight')?.value, 10) || 300;

    const pkgWidth = isPkgAdder ? (rawWidth + 10) : rawWidth;
    const pkgLength = isPkgAdder ? (rawLength + 10) : rawLength;
    const pkgHeight = isPkgAdder ? (rawHeight + 10) : rawHeight;
    const pkgWeight = isPkgAdder ? (rawWeight + 30) : rawWeight;
    const dimStr = `${pkgWidth}х${pkgLength}х${pkgHeight}`;

    const payload = {
      template_mode: window.currentTemplateMode || 'pre2011',
      article: article,
      barcode: barcodeVal,
      isbn: (window.currentTemplateMode === 'pre2011') ? isbnVal : (isbnVal || '978-5-0000-0000-0'),
      title: title,
      original_title: (document.getElementById('original_title')?.value || '').trim(),
      series: document.getElementById('series')?.value?.trim() || '',
      author_cover: authorCover,
      author: author,
      illustrator: document.getElementById('illustrator')?.value?.trim() || '',
      translator: document.getElementById('translator')?.value?.trim() || '',
      publisher: publisherVal,
      brand: document.getElementById('brand')?.value?.trim() || 'Нет бренда',
      year: document.getElementById('year')?.value?.trim() || '',
      pages: document.getElementById('pages')?.value?.trim() || '',
      country: document.getElementById('country')?.value || 'Россия',
      cover_type: document.getElementById('cover_type')?.value || 'Твердый переплет',
      paper_type: paperType,
      genre: document.getElementById('genre')?.value || 'Проза',
      age_limit: document.getElementById('age_limit')?.value || '',
      target_audience: '',
      condition: document.getElementById('condition')?.value || 'Очень хорошая',
      defects: '',
      annotation: document.getElementById('annotation')?.value?.trim() || '',
      hashtags: '',
      price: String(priceVal),
      old_price: document.getElementById('old_price')?.value?.trim() || '',
      dimensions: dimStr,
      weight: rawWeight,
      width: rawWidth,
      length: rawLength,
      height: rawHeight,
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
        name: p.name || 'photo.jpg',
        s3_url: p.s3_url || null,
        is_s3_uploaded: Boolean(p.is_s3_uploaded),
      };
    };

    const book = typeof window.getActiveBook === 'function' ? window.getActiveBook() : null;
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
        const photoMsg = photoCount > 0 ? ` (в архив и S3 сохранено ${photoCount} фото${s3Badge})` : '';
        const today = typeof window.getTodayStr === 'function' ? window.getTodayStr() : '';
        const fileName = result.file_name || ((result.template_mode === 'pre2011') ? `${today}_Печатная книга_до_2011.xlsx` : `${today}_Печатная книга_после_2011.xlsx`);
        const targetFolder = result.folder || ((result.template_mode === 'pre2011') ? 'ready_tables/1942-2010' : 'ready_tables/с_2011');
        const status = document.getElementById('formStatus');
        if (status) {
          status.textContent = `✅ Книга "${result.title}" записана в ${targetFolder}/${fileName} (строка ${result.row})!${photoMsg}`;
          status.className = 'text-center text-xs text-emerald-400 font-semibold';
        }
        if (typeof window.showToast === 'function') {
          window.showToast(`✅ Записано в <b>${targetFolder}/${fileName}</b> (строка ${result.row})${s3Badge}`);
        }

        if (book) book.isSavedToExcel = true;
        if (typeof window.loadCatalogReferences === 'function') window.loadCatalogReferences();
        if (typeof window.renderBooksTabs === 'function') window.renderBooksTabs();
        if (typeof window.scheduleAutoSave === 'function') window.scheduleAutoSave();

        // Предлагаем перейти к следующей книге если есть неразобранные фото
        const unassigned = (window.photoPool || []).filter(p => !p.assignedBookId).length;
        if (unassigned > 0) {
          const templateLabel = (result.template_mode === 'pre2011') ? 'До 2011 г.' : 'После 2011 г.';
          setTimeout(() => {
            if (confirm(`Книга сохранена в шаблон (${templateLabel})! В пуле осталось ${unassigned} неразобранных фото. Создать карточку следующей книги?`)) {
              if (typeof window.addNewBook === 'function') window.addNewBook();
            }
          }, 600);
        }
      } else {
        alert('Ошибка записи: ' + (result.error || 'Неизвестная ошибка'));
      }
    } catch (err) {
      alert('Ошибка записи: ' + err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span>💾</span> <span>Записать книгу в Excel Ozon (Cmd + Enter)</span>';
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
        if (window.cropperInstance && window.cropperInstance.cropped) {
          if (typeof window.resetCropToOriginal === 'function') window.resetCropToOriginal();
        } else {
          if (typeof window.closePhotoStudio === 'function') window.closePhotoStudio(false);
        }
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
          if (typeof window.applyStudioPreset === 'function') window.applyStudioPreset('studio_white');
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
      if (typeof window.closePhotoStudio === 'function') window.closePhotoStudio(false);
      if (typeof window.closeQrModal === 'function') window.closeQrModal();
      if (typeof window.closeKeyModal === 'function') window.closeKeyModal();
      if (typeof window.closeCardModal === 'function') window.closeCardModal();
      if (typeof window.closeClearTableModal === 'function') window.closeClearTableModal();
    }
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      saveBookToExcel();
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
      const initArt = (typeof window.calculateNextArticle === 'function') ? await window.calculateNextArticle(0) : 'DP-B-00001';
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

})(window);
