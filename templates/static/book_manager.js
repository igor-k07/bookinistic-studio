/**
 * book_manager.js: Сессии книг, валидация полей, EAN-13, расчет габаритов, автосохранение и экспорт в Excel/Vault.
 */

    function setTemplateMode(mode, userInitiated = true) {
      if (userInitiated) {
        if (mode === currentTemplateMode) return;
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

      currentTemplateMode = (mode === 'post2011') ? 'post2011' : 'pre2011';
      const btnPre = document.getElementById('btnModePre');
      const btnPost = document.getElementById('btnModePost');
      const isbnStar = document.getElementById('isbnStar');
      const isbnNote = document.getElementById('isbnNote');
      const isbnInput = document.getElementById('isbn');

      if (currentTemplateMode === 'pre2011') {
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

      const book = getActiveBook();
      if (book) {
        if (!book.formData) book.formData = {};
        book.formData.template_mode = currentTemplateMode;
      }
      if (typeof switchPreviewTable === 'function') {
        switchPreviewTable(currentTemplateMode, false);
      }
      scheduleAutoSave();
    }

    function onYearInput(val) {
      autoDetectCountry();
      const y = parseInt(val);
      if (!isNaN(y) && y > 1000 && y < 2100) {
        const targetMode = (y <= 2011) ? 'pre2011' : 'post2011';
        if (targetMode !== currentTemplateMode) {
          setTemplateMode(targetMode, false);
          if (typeof switchPreviewTable === 'function') {
            switchPreviewTable(targetMode, true);
          }
        }
      }
    }

    // -------------------------------------------------------------
    // АВТОСОХРАНЕНИЕ И ВОССТАНОВЛЕНИЕ ПОДГОТОВЛЕННЫХ КНИГ (DRAFT PERSISTENCE)
    // -------------------------------------------------------------
    function scheduleAutoSave() {
      saveCurrentFormToActiveBook();
      updateAutoSaveStatus('saving');
      clearTimeout(autoSaveTimer);
      autoSaveTimer = setTimeout(performAutoSave, 500);
    }

    async function performAutoSave() {
      saveCurrentFormToActiveBook();
      try {
        // Компактный photoPool без раздутой истории undo и дубликатов data
        const cleanPool = photoPool.map(p => {
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
          return item;
        });

        // Де-дуплицированные слоты книг (только id)
        const cleanBooks = booksSession.map(b => {
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
          activeBookId: activeBookId,
          booksSession: cleanBooks,
          photoPool: cleanPool,
          timestamp: Date.now()
        };

        const res = await fetch('/api/save_session_draft', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          const resData = await res.json();
          if (resData.success && resData.updated_urls) {
            // Освобождаем память в браузере, заменяя base64 на легкие локальные URL
            Object.keys(resData.updated_urls).forEach(pid => {
              const p = findPhotoById(pid);
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
        const res = await fetch('/api/get_session_draft');
        if (!res.ok) return false;
        const draft = await res.json();
        if (draft && draft.booksSession && draft.booksSession.length > 0) {
          booksSession = draft.booksSession;
          photoPool = draft.photoPool || [];
          activeBookId = draft.activeBookId || booksSession[0].id;
          // Санитизация аннотаций: убираем предупреждения из черновика для книг без дефектов
          booksSession.forEach(b => {
            const hasDefects = Boolean(b.slots && b.slots.mantra_defects && b.slots.mantra_defects.length > 0);
            if (!hasDefects && b.formData && b.formData.annotation) {
              b.formData.annotation = cleanAnnotationText(b.formData.annotation);
            }
          });
          relinkSessionPhotos();
          renderBooksTabs();
          restoreFormFromActiveBook();
          renderActiveBookSlots();
          renderPool();
          autoCalcDimensions();
          autoDetectCountry();
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
      photoPool.forEach(p => {
        if (!p.cameraOriginal) p.cameraOriginal = p.rawOriginal || p.preview;
        if (!p.rawOriginal) p.rawOriginal = p.cameraOriginal;
        if (!p.preview) p.preview = p.cameraOriginal || p.rawOriginal || (p.data ? ('data:' + (p.mime || 'image/jpeg') + ';base64,' + p.data) : '');
        if (p.isCropped === undefined) p.isCropped = Boolean(p.croppedBase);
        if (p.croppedBase === undefined) p.croppedBase = null;
        p.isProcessed = isPhotoProcessed(p);
        map.set(p.id, p);
      });

      booksSession.forEach(b => {
        if (!b.slots) b.slots = {};
        if (b.slots.cover_front && b.slots.cover_front.id) {
          if (map.has(b.slots.cover_front.id)) {
            b.slots.cover_front = map.get(b.slots.cover_front.id);
          } else if (b.slots.cover_front.preview) {
            photoPool.push(b.slots.cover_front);
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
              photoPool.push(p);
              map.set(p.id, p);
              return p;
            }
            return null;
          }).filter(Boolean);
        });
      });
    }

    async function resetCurrentBook() {
      const book = getActiveBook();
      if (!book) return;

      const art = (book.formData && book.formData.article) || book.article || `Книга #${book.id}`;
      if (!confirm(`Сбросить все заполненные блоки и слоты для ${art}?` + '\\n\\n' + 'Все прикрепленные фотографии этой книги вернутся в свободный пул.')) {
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
      await clearForm(book.article);
      if (document.getElementById('autoPackageAdder')) {
        document.getElementById('autoPackageAdder').checked = true;
      }
      book.formData = {
        article: book.article,
        article_number: book.article.replace(/\D/g, '').slice(-5),
        barcode: document.getElementById('barcode').value,
        template_mode: currentTemplateMode,
        auto_package_adder: true
      };
      autoCalcDimensions();

      // 3. Обновляем интерфейс: освобожденные фото сразу вернутся в пул
      renderBooksTabs();
      renderActiveBookSlots();
      renderPool();
      scheduleAutoSave();
    }

    async function resetWholeSession() {
      // По запросу пользователя кнопка "Сбросить всё" сбрасывает именно текущую книгу
      return resetCurrentBook();
    }

    window.addEventListener('DOMContentLoaded', async () => {
      setTemplateMode('pre2011', false);
      loadSavedKey();
      loadOzonStatus();
      updateBooksCount();
      refreshPreviewTable('pre2011');
      loadMobileUrl();
      loadCatalogReferences();
      startMobileEventListener();
      initRotaryDial();

      // Подключаем слушатели на контейнер карточки Ozon для мгновенного сохранения изменений
      const formContainer = document.getElementById('ozonFormContainer');
      if (formContainer) {
        formContainer.addEventListener('input', scheduleAutoSave);
        formContainer.addEventListener('change', scheduleAutoSave);
      }

      // Пытаемся восстановить черновик сессии при перезагрузке страницы
      const restored = await restoreSessionDraft();
      if (!restored) {
        const initArt = await calculateNextArticle(0);
        if (booksSession[0]) {
          booksSession[0].article = initArt;
          if (!booksSession[0].formData) booksSession[0].formData = {};
          booksSession[0].formData.article = initArt;
        }
        renderBooksTabs();
        renderActiveBookSlots();
        clearForm(initArt);
        autoCalcDimensions();
      }
      initBatchArticleInput();
    });

    async function initBatchArticleInput() {
      const el = document.getElementById('batchStartArticle');
      if (el && !el.value) {
        const nextArt = await calculateNextArticle(0);
        el.value = nextArt;
      }
    }



// -------------------------------------------------------------
// СЕССИИ КНИГ, ШТРИХКОДЫ И СИНХРОНИЗАЦИЯ ФОРМЫ
// -------------------------------------------------------------
    // УПРАВЛЕНИЕ КНИГАМИ И СЛОТАМИ
    // -------------------------------------------------------------
    function getActiveBook() {
      return booksSession.find(b => b.id === activeBookId) || booksSession[0];
    }

    async function calculateNextArticle(offset = 0) {
      // 1. Ищем максимальный номер среди книг ТЕКУЩЕЙ СЕССИИ booksSession
      let maxSessionNum = 0;
      if (typeof booksSession !== 'undefined' && Array.isArray(booksSession)) {
        booksSession.forEach(b => {
          const art = (b.formData && (b.formData.article || b.formData.article_number)) || b.article || '';
          const digits = String(art).replace(/\D/g, '');
          if (digits) {
            const val = parseInt(digits, 10);
            if (val > maxSessionNum) maxSessionNum = val;
          }
        });
      }

      // Если в текущей сессии уже есть хотя бы один номер книги,
      // то каждая новая книга в этой сессии создается строго по порядку (+1 к максимальному номеру сессии)
      if (maxSessionNum > 0) {
        const nextNum = maxSessionNum + 1;
        return `DP-B-${String(nextNum).padStart(5, '0')}`;
      }

      // 2. Если сессия пустая, подтягиваем из базы Excel
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

    function calcEan13Checksum(digits12) {
      const d = String(digits12).replace(/\D/g, '');
      if (d.length !== 12) return 0;
      let sOdd = 0, sEven = 0;
      for (let i = 0; i < 12; i++) {
        const val = parseInt(d[i], 10);
        if (i % 2 === 0) sOdd += val;
        else sEven += val;
      }
      const total = sOdd + sEven * 3;
      return (10 - (total % 10)) % 10;
    }

    const STORE_BARCODE_PREFIX = '297847'; // 29 (GS1) + 78 (СПб) + 47 (Другой Петербург: D=4, P=7)

    function generateEan13FromArticle(article) {
      const digits = String(article || '').replace(/\D/g, '');
      let num = parseInt(digits, 10);
      if (isNaN(num) || num <= 0) num = 1;
      const base12 = (STORE_BARCODE_PREFIX + String(num).padStart(6, '0')).slice(-12);
      const check = calcEan13Checksum(base12);
      return `${base12}${check}`;
    }

    function generateBarcodeForCurrentBook() {
      const artInput = document.getElementById('article');
      let art = artInput ? artInput.value.trim() : '';
      if (!art) {
        art = 'DP-B-00001';
        if (artInput) artInput.value = art;
      }
      const barcode = generateEan13FromArticle(art);
      const bcInput = document.getElementById('barcode');
      if (bcInput) {
        bcInput.value = barcode;
        bcInput.classList.add('field-updated');
        setTimeout(() => bcInput.classList.remove('field-updated'), 1000);
      }
      const book = getActiveBook();
      if (book) {
        if (!book.formData) book.formData = {};
        book.formData.barcode = barcode;
      }
      scheduleAutoSave();
    }

    function generateEan13Svg(eanStr) {
      const ean = String(eanStr || '').replace(/\D/g, '');
      if (ean.length !== 13) {
        return `<div class="text-[10px] text-rose-500 font-mono py-2">Некорректный EAN-13 (${ean.length} цифр)</div>`;
      }
      const L = {'0':'0001101','1':'0011001','2':'0010011','3':'0111101','4':'0100011','5':'0110001','6':'0101111','7':'0111011','8':'0110111','9':'0001011'};
      const G = {'0':'0100111','1':'0110011','2':'0011011','3':'0100001','4':'0011101','5':'0111001','6':'0000101','7':'0010001','8':'0001001','9':'0010111'};
      const R = {'0':'1110010','1':'1100110','2':'1101100','3':'1000010','4':'1011100','5':'1001110','6':'1010000','7':'1000100','8':'1001000','9':'1110100'};
      const P = {'0':'LLLLLL','1':'LLGLGG','2':'LLGGLG','3':'LLGGGL','4':'LGLLGG','5':'LGGLLG','6':'LGGGLL','7':'LGLGLG','8':'LGLGGL','9':'LGGLGL'};

      const parity = P[ean[0]];
      const isGuard = (idx) => (idx < 3 || (idx >= 45 && idx < 50) || idx >= 92);

      let bitStr = '101';
      for (let i = 0; i < 6; i++) {
        const d = ean[1 + i];
        bitStr += (parity[i] === 'L') ? L[d] : G[d];
      }
      bitStr += '01010';
      for (let i = 0; i < 6; i++) {
        const d = ean[7 + i];
        bitStr += R[d];
      }
      bitStr += '101';

      const moduleWidth = 2;
      const barHeightNormal = 38;
      const barHeightGuard = 44;
      const totalBarWidth = 95 * moduleWidth;
      const leftQuiet = 14;
      const svgWidth = totalBarWidth + leftQuiet + 14;
      const svgHeight = 58;

      let rects = '';
      for (let i = 0; i < bitStr.length; i++) {
        if (bitStr[i] === '1') {
          const h = isGuard(i) ? barHeightGuard : barHeightNormal;
          const x = leftQuiet + i * moduleWidth;
          rects += `<rect x="${x}" y="0" width="${moduleWidth}" height="${h}" fill="#000000" />`;
        }
      }

      const d0 = ean[0];
      const dLeft = ean.slice(1, 7);
      const dRight = ean.slice(7, 13);
      const textLeftX = leftQuiet + 3 * moduleWidth + (42 * moduleWidth) / 2;
      const textRightX = leftQuiet + 48 * moduleWidth + (42 * moduleWidth) / 2;

      return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${svgWidth} ${svgHeight}" class="w-full h-auto max-h-[54px]" shape-rendering="crispEdges">` +
        `<rect width="${svgWidth}" height="${svgHeight}" fill="#ffffff" />` +
        rects +
        `<text x="${leftQuiet - 4}" y="50" font-family="monospace, monospace" font-size="11" font-weight="bold" fill="#000" text-anchor="end">${d0}</text>` +
        `<text x="${textLeftX}" y="51" font-family="monospace, monospace" font-size="11" letter-spacing="1.2" fill="#000" text-anchor="middle">${dLeft}</text>` +
        `<text x="${textRightX}" y="51" font-family="monospace, monospace" font-size="11" letter-spacing="1.2" fill="#000" text-anchor="middle">${dRight}</text>` +
      `</svg>`;
    }

    function openBarcodeModal() {
      const book = getActiveBook();
      let art = document.getElementById('article')?.value.trim() || (book?.formData?.article) || 'DP-B-00001';
      let bc = document.getElementById('barcode')?.value.trim() || (book?.formData?.barcode) || '';
      if (!bc || bc === 'генерирует озон' || !/^\d{12,13}$/.test(bc)) {
        bc = generateEan13FromArticle(art);
        const bcInput = document.getElementById('barcode');
        if (bcInput) bcInput.value = bc;
      }
      const title = document.getElementById('title')?.value.trim() || (book?.formData?.title) || 'Книга';
      const author = document.getElementById('author')?.value.trim() || document.getElementById('author_cover')?.value.trim() || (book?.formData?.author) || '';
      const price = document.getElementById('price')?.value.trim() || (book?.formData?.price) || '350';

      const labelTitle = document.getElementById('labelTitle');
      const labelAuthor = document.getElementById('labelAuthor');
      const labelArticle = document.getElementById('labelArticle');
      const labelPrice = document.getElementById('labelPrice');
      const labelEanText = document.getElementById('labelEanText');
      const svgBox = document.getElementById('barcodeSvgContainer');

      if (labelTitle) labelTitle.textContent = title;
      if (labelAuthor) labelAuthor.textContent = author || 'Букинистика';
      if (labelArticle) labelArticle.textContent = art;
      if (labelPrice) labelPrice.textContent = price ? `${price} ₽` : '350 ₽';
      if (labelEanText) labelEanText.textContent = bc;
      if (svgBox) svgBox.innerHTML = generateEan13Svg(bc);

      const modal = document.getElementById('barcodeModal');
      if (modal) modal.classList.remove('hidden');
    }

    function closeBarcodeModal() {
      const modal = document.getElementById('barcodeModal');
      if (modal) modal.classList.add('hidden');
    }

    function printBarcodeLabel() {
      window.print();
    }

    async function copyBarcodeText() {
      const el = document.getElementById('labelEanText');
      const bc = el ? el.textContent.trim() : '';
      try {
        await navigator.clipboard.writeText(bc);
        const icon = document.getElementById('copyBarcodeIcon');
        const text = document.getElementById('copyBarcodeBtnText');
        if (icon) icon.textContent = '✅';
        if (text) text.textContent = 'Скопировано!';
        setTimeout(() => {
          if (icon) icon.textContent = '📋';
          if (text) text.textContent = 'Копировать код';
        }, 1500);
      } catch (e) {
        alert(`Штрихкод: ${bc}`);
      }
    }

    async function addNewBook() {
      saveCurrentFormToActiveBook();
      const nextId = booksSession.length > 0 ? Math.max(...booksSession.map(b => b.id)) + 1 : 1;
      const nextArt = await calculateNextArticle(booksSession.length);
      const nextBarcode = generateEan13FromArticle(nextArt);
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
      booksSession.push(newBook);
      activeBookId = nextId;
      renderBooksTabs();
      renderActiveBookSlots();
      clearForm(nextArt);
      scheduleAutoSave();
    }

    function deleteBookSession(id, e) {
      if (e) e.stopPropagation();
      if (booksSession.length <= 1) {
        alert('В сессии должна оставаться как минимум одна книга!');
        return;
      }
      if (!confirm('Удалить эту карточку книги из текущей сессии? Фото вернутся в общий пул.')) return;
      
      photoPool.forEach(p => {
        if (p.assignedBookId === id) {
          p.assignedBookId = null;
          p.assignedSlot = null;
        }
      });
      
      booksSession = booksSession.filter(b => b.id !== id);
      if (activeBookId === id) {
        activeBookId = booksSession[0].id;
      }
      renderPool();
      renderBooksTabs();
      restoreFormFromActiveBook();
      renderActiveBookSlots();
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

      const book = getActiveBook();
      if (book) {
        book.article = fullArt;
        if (!book.formData) book.formData = {};
        book.formData.article = fullArt;
        book.formData.article_number = digits;

        const bcEl = document.getElementById('barcode');
        const curBc = bcEl ? bcEl.value.trim() : '';
        if (!curBc || curBc === 'генерирует озон' || curBc.startsWith('29')) {
          const newBc = generateEan13FromArticle(fullArt);
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
          const book = getActiveBook();
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
      const book = getActiveBook();
      if (!book) return;
      book.article = fullArt;
      if (!book.formData) book.formData = {};
      book.formData.article = fullArt;
      book.formData.article_number = fullArt.replace(/\D/g, '').slice(-5);

      const bcEl = document.getElementById('barcode');
      const curBc = bcEl ? bcEl.value.trim() : '';
      if (!curBc || curBc === 'генерирует озон' || curBc.startsWith('29')) {
        const newBc = generateEan13FromArticle(fullArt);
        if (bcEl) bcEl.value = newBc;
        book.formData.barcode = newBc;
      }

      renderBooksTabs();
      scheduleAutoSave();
    }

    function onBarcodeInput(val) {
      const book = getActiveBook();
      if (!book) return;
      if (!book.formData) book.formData = {};
      book.formData.barcode = val.trim();
      scheduleAutoSave();
    }

    function onTitleInput(val) {
      const book = getActiveBook();
      if (!book) return;
      if (!book.formData) book.formData = {};
      book.formData.title = val;
      renderBooksTabs();
      scheduleAutoSave();
    }

    const FORM_FIELD_IDS = [
      'article', 'article_number', 'barcode', 'isbn', 'title', 'original_title', 'series', 'author_cover', 'author',
      'illustrator', 'translator', 'publisher', 'brand', 'year', 'country', 'pages', 'cover_type',
      'paper_type', 'genre', 'age_limit', 'target_audience', 'condition',
      'annotation', 'hashtags', 'price', 'old_price', 'dimensions', 'weight',
      'width', 'length', 'height',
      'width_package', 'length_package', 'height_package', 'weight_package'
    ];

    function saveCurrentFormToActiveBook() {
      const book = getActiveBook();
      if (!book) return;
      if (!book.formData) book.formData = {};
      FORM_FIELD_IDS.forEach(id => {
        const el = document.getElementById(id);
        if (el) book.formData[id] = el.value;
      });
      if (document.getElementById('autoPackageAdder')) {
        book.formData.auto_package_adder = document.getElementById('autoPackageAdder').checked;
      }
      book.formData.template_mode = currentTemplateMode;
      if (book.formData.article) book.article = book.formData.article;
    }

    function restoreFormFromActiveBook() {
      const book = getActiveBook();
      if (!book) return;
      if (!book.formData) book.formData = {};

      // Гарантированно очищаем или заполняем каждое поле формы из book.formData текущей книги
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
        book.formData['genre'] = (typeof resolveOzonGenre === 'function')
          ? resolveOzonGenre(book.formData['genre'], book.formData['title'], book.formData['annotation'])
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
      if (defectCount === 0) {
        setCondition('Очень хорошая', false);
      } else if (book.formData && book.formData.condition === 'Удовлетворительная') {
        setCondition('Удовлетворительная', false);
      } else {
        setCondition('Хорошая', false);
      }
      const mode = book.formData.template_mode || (parseInt(book.formData.year) > 2011 ? 'post2011' : 'pre2011');
      setTemplateMode(mode, false);
      updateDimensionsPreviewBadge();
      // Синхронизируем предупреждение строго после восстановления полей формы
      syncAnnotationWarningWithDefectsSlot();
    }

    function switchBook(id) {
      if (activeBookId === id) return;
      saveCurrentFormToActiveBook();
      activeBookId = id;
      renderBooksTabs();
      restoreFormFromActiveBook();
      renderActiveBookSlots();
      scheduleAutoSave();
    }

    function renderBooksTabs() {
      const container = document.getElementById('booksTabsContainer');
      container.innerHTML = booksSession.map(b => {
        const isActive = b.id === activeBookId;
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
            ${booksSession.length > 1 ? `
              <button type="button" onclick="deleteBookSession(${b.id}, event)" class="px-2 py-1.5 text-xs ${isActive ? 'text-slate-950 hover:bg-amber-400 hover:text-rose-950' : 'text-slate-400 hover:bg-slate-700 hover:text-rose-400'} transition font-bold" title="Удалить карточку этой книги">✕</button>
            ` : ''}
          </div>
        `;
      }).join('');
      const cur = getActiveBook();
      const curArt = (cur.formData && cur.formData.article) || cur.article || `Книга #${cur.id}`;
      document.getElementById('activeBookTitle').textContent = `📚 [${curArt}]: Слоты категорий`;
    }



// -------------------------------------------------------------
// ИИ-РАСПОЗНАВАНИЕ ПОЛЕЙ, РАСЧЕТ ГАБАРИТОВ И СОВЕТСКИХ ФОРМАТОВ
// -------------------------------------------------------------
    // -------------------------------------------------------------
    // РУЧНАЯ СВЕРКА С БАЗОЙ (FANTLAB / OPEN LIBRARY)
    // -------------------------------------------------------------
    async function runManualEnrichment() {
      const title = document.getElementById('title')?.value?.trim() || '';
      const isbn = document.getElementById('isbn')?.value?.trim() || '';
      if (!title && !isbn) {
        alert('Укажите название книги или ISBN для сверки с базой FantLab!');
        return;
      }
      const curBook = getActiveBook();
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
        const res = await fetch('/api/enrich_book', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ book: bookPayload, has_illustrations: hasIllustrations, skip_dimensions: true })
        });
        const json = await res.json();
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
            showToast(`🎯 FantLab: карточка уточнена по ISBN ${matchedIsbn}`);
          } else {
            const vSource = json.data.verified_by || 'База проверена';
            if (fs) {
              fs.textContent = `✓ Данные сверены с базой (${vSource}), недостающие поля дополнены.`;
              fs.className = 'text-center text-xs text-cyan-400 font-semibold';
            }
            showToast(`✓ Сверка с базой завершена (${vSource})`);
          }
        } else {
          if (fs) {
            fs.textContent = 'ℹ️ Точных совпадений в базе FantLab не найдено.';
            fs.className = 'text-center text-xs text-slate-400 font-medium';
          }
          showToast('ℹ️ В базе FantLab совпадений не найдено');
        }
      } catch (err) {
        console.error('Ошибка в runManualEnrichment:', err);
        if (fs) {
          fs.textContent = '⚠️ Не удалось связаться с базой.';
          fs.className = 'text-center text-xs text-rose-400';
        }
        showToast('⚠️ Ошибка соединения с FantLab');
      }
    }

    function populateFields(data, targetBook = null) {
      if (!data) return;
      const curBookObj = targetBook || getActiveBook();
      if (!curBookObj) return;
      if (!curBookObj.formData) curBookObj.formData = {};

      const isCurrentActive = (curBookObj.id === activeBookId);

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

        // Бренд Ozon: всегда пытаемся скопировать название издательства в бренд,
        // сверяем с базой брендов, и только если в базе нет — ставим "Нет бренда"
        const pubForBrand = data.publisher || (isCurrentActive ? document.getElementById('publisher')?.value : (curBookObj.formData && curBookObj.formData.publisher)) || '';
        let targetBrand = data.brand;
        if (!targetBrand || targetBrand === 'Нет бренда' || targetBrand.toLowerCase() === 'не указан') {
          targetBrand = (typeof resolveBrandFromPublisher === 'function') ? resolveBrandFromPublisher(pubForBrand) : 'Нет бренда';
        } else {
          const verified = (typeof resolveBrandFromPublisher === 'function') ? resolveBrandFromPublisher(targetBrand) : targetBrand;
          targetBrand = (verified !== 'Нет бренда') ? verified : ((typeof resolveBrandFromPublisher === 'function') ? resolveBrandFromPublisher(pubForBrand) : 'Нет бренда');
        }
        fill('brand', targetBrand || 'Нет бренда');
        const recognizedYear = data.year ? parseInt(data.year, 10) : 0;
        if (data.year) {
          fill('year', data.year);
          if (isCurrentActive) {
            try { onYearInput(data.year); } catch (e) { console.warn('onYearInput error', e); }
          }
        }

        // Правило: если книга до 2011 года и ISBN не был распознан на 100% прямо с фото — строго не указывать
        // Исключение: при точном подтверждении ISBN из базы (exact_isbn_match) ISBN гарантированно сохраняется
        const isPre2011 = (recognizedYear > 0 && recognizedYear <= 2011) || currentTemplateMode === 'pre2011';
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
        } else if (currentTemplateMode === 'post2011') {
          fill('isbn', '978-5-0000-0000-0');
        } else if (data.isbn !== undefined) {
          fill('isbn', '', true);
        }
        let bcVal = data.barcode ? String(data.barcode).trim() : '';
        if (!bcVal || bcVal === 'генерирует озон' || !/^\d{12,13}$/.test(bcVal)) {
          const curArt = curBookObj.formData.article || curBookObj.article || 'DP-B-00001';
          bcVal = generateEan13FromArticle(curArt);
        }
        fill('barcode', bcVal);
        if (data.series) fill('series', data.series);
        if (data.pages) fill('pages', data.pages);

        // Аннотация:
        // Если новая аннотация передана (от Gemini) — используем её.
        // Если в data аннотации нет (при сверке с FantLab) — сохраняем ТЕКУЩИЙ текст именно этой книги!
        if (data.annotation !== undefined && data.annotation !== null) {
          const incomingAnt = String(data.annotation).trim();
          if (incomingAnt) {
            let cleanAnt = cleanAnnotationText(incomingAnt);
            const hasMantraDefects = Boolean(curBookObj.slots && curBookObj.slots.mantra_defects && curBookObj.slots.mantra_defects.length > 0);
            let fullAnt = cleanAnt;
            if (hasMantraDefects && cleanAnt) {
              fullAnt = ANNOTATION_WARNING + '\n\n' + cleanAnt;
            }
            curBookObj.formData.annotation = fullAnt;
            if (isCurrentActive) {
              const antEl = document.getElementById('annotation');
              if (antEl) {
                antEl.value = fullAnt;
                antEl.classList.add('field-updated');
                setTimeout(() => antEl.classList.remove('field-updated'), 1200);
              }
              syncAnnotationWarningWithDefectsSlot();
            }
          }
        }

        if (data.translator) fill('translator', data.translator);

        // Правило: иллюстратора указываем ТОЛЬКО если в слоте иллюстраций есть реальные фото
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
          const resolvedGenre = (typeof resolveOzonGenre === 'function')
            ? resolveOzonGenre(rawG, curTitle, curAnnot)
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
          const p = parseInt(data.suggested_price);
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
          try { saveCurrentFormToActiveBook(); } catch (e) { console.warn('saveCurrentFormToActiveBook error', e); }
        }
        try { renderBooksTabs(); } catch (e) { console.warn('renderBooksTabs error', e); }
        try { scheduleAutoSave(); } catch (e) { console.warn('scheduleAutoSave error', e); }
      } catch (err) {
        console.error('Ошибка в populateFields:', err);
      }
    }

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
      const curBook = getActiveBook();
      const defectCount = (curBook && curBook.slots && curBook.slots.mantra_defects) ? curBook.slots.mantra_defects.length : 0;
      const hasDefects = defectCount > 0;

      let normalized = cond || 'Очень хорошая';
      if (normalized === 'Отличная' || normalized === 'Очень хорошее') normalized = 'Очень хорошая';
      if (normalized === 'Хорошее') normalized = 'Хорошая';
      if (normalized === 'Удовлетворительное') normalized = 'Удовлетворительная';
      if (normalized === 'Плохая' || normalized === 'Плохое') normalized = 'Хорошая';

      // Правило регламента:
      // 1. «Очень хорошее» — когда нет фото дефектов ВСЕГДА.
      if (!hasDefects) {
        if (isUserManual && (normalized === 'Хорошая' || normalized === 'Удовлетворительная')) {
          showToast('💡 В слоте [5. Дефекты] нет фото — для книги всегда действует «Очень хорошее».');
        }
        normalized = 'Очень хорошая';
      } else {
        // 2. Если есть хотя бы 1 дефект — состояние «Хорошее», но не меньше.
        // 3. «Удовлетворительное» можно поставить ТОЛЬКО вручную.
        if (normalized === 'Очень хорошая') {
          if (isUserManual) {
            showToast('⚠️ В слоте [5. Дефекты] есть фото: сохранность не может быть «Очень хорошее».');
          }
          normalized = 'Хорошая';
        }
        // Автоматика никогда не ставит Удовлетворительное сама — только если пользователь уже выставил его вручную:
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


    function onDimensionChange() {
      const isPkgAdder = document.getElementById('autoPackageAdder')?.checked !== false;

      const wEl = document.getElementById('width');
      const lEl = document.getElementById('length');
      const hEl = document.getElementById('height');
      const wtEl = document.getElementById('weight');

      const rawW = (wEl && parseInt(wEl.value)) || 130;
      const rawL = (lEl && parseInt(lEl.value)) || 205;
      const rawH = (hEl && parseInt(hEl.value)) || 22;
      const rawWt = (wtEl && parseInt(wtEl.value)) || 300;

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

      saveCurrentFormToActiveBook();
      scheduleAutoSave();
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
      const pages = parseInt(document.getElementById('pages')?.value) || 200;
      const widthEl = document.getElementById('width');
      const lengthEl = document.getElementById('length');
      const heightEl = document.getElementById('height');
      const weightEl = document.getElementById('weight');

      let w = (widthEl && parseInt(widthEl.value)) || 130;
      let l = (lengthEl && parseInt(lengthEl.value)) || 205;
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
      const year = parseInt(document.getElementById('year').value) || 0;
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
      // Целевая аудитория исключена по правилам каталогизации
      const ta = document.getElementById('target_audience');
      if (ta) ta.value = '';
    }


    async function generateNewArticle() {
      const book = getActiveBook();
      const idx = booksSession.indexOf(book);
      const nextArt = await calculateNextArticle(idx >= 0 ? idx : 0);
      document.getElementById('article').value = nextArt;
      onArticleInput(nextArt);
    }

    function generateArticleByAuthor() {
      const author = document.getElementById('author').value.trim() || document.getElementById('author_cover').value.trim();
      const year = document.getElementById('year').value.trim();
      if (!author) {
        alert('Сначала укажите автора или распознайте книгу через ИИ!');
        return;
      }
      const words = author.replace(/[^A-Za-zА-Яа-я0-9\s]/g, '').trim().split(/\s+/);
      const surname = (words[0] || 'BOOK').toUpperCase();
      const suffix = year ? `-${year}` : `-${String(activeBookId).padStart(2, '0')}`;
      const art = `${surname}${suffix}`;
      document.getElementById('article').value = art;
      onArticleInput(art);
    }

    function calcEan13Checksum(digits12) {
      let sum = 0;
      for (let i = 0; i < 12; i++) {
        sum += parseInt(digits12[i], 10) * (i % 2 === 0 ? 1 : 3);
      }
      return ((10 - (sum % 10)) % 10).toString();
    }

    function deriveBarcodeFromIsbn() {
      const isbn = document.getElementById('isbn').value.trim();
      const digits = isbn.replace(/\D/g, '');
      let finalBarcode = '';
      if (digits.length === 13) {
        finalBarcode = digits;
      } else if (digits.length === 10) {
        const base12 = '978' + digits.substring(0, 9);
        finalBarcode = base12 + calcEan13Checksum(base12);
      } else {
        alert(`В поле ISBN должно быть 10 или 13 цифр (например: 978-5-17-147716-5)! Сейчас там: "${isbn}"`);
        return;
      }

      document.getElementById('barcode').value = finalBarcode;
      onBarcodeInput(finalBarcode);
      const el = document.getElementById('barcode');
      el.classList.add('field-updated');
      setTimeout(() => el.classList.remove('field-updated'), 1000);
      showToast(`Штрихкод установлен из ISBN: <b>${finalBarcode}</b>`);
    }

    async function clearForm(customArt = null) {
      ['title', 'original_title', 'author_cover', 'author', 'series', 'illustrator', 'translator', 'publisher', 'year', 'pages', 'price', 'old_price'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.value = '';
      });
      document.getElementById('annotation').value = '';
      syncAnnotationWarningWithDefectsSlot();
      document.getElementById('brand').value = 'Нет бренда';
      if (document.getElementById('autoPackageAdder')) {
        document.getElementById('autoPackageAdder').checked = true;
      }
      if (currentTemplateMode === 'pre2011') {
        document.getElementById('isbn').value = '';
      } else {
        document.getElementById('isbn').value = '978-5-0000-0000-0';
      }
      document.getElementById('country').value = 'Россия';
      document.getElementById('cover_type').value = 'Твердый переплет';
      document.getElementById('paper_type').value = '';
      document.getElementById('genre').value = 'Проза';
      document.getElementById('age_limit').value = '';
      document.getElementById('target_audience').value = '';
      if (document.getElementById('hashtags')) document.getElementById('hashtags').value = '';

      const book = getActiveBook();
      let art = customArt;
      if (!art && book && (book.article || (book.formData && book.formData.article))) {
        art = (book.formData && book.formData.article) || book.article;
      }
      if (!art) {
        const idx = booksSession.indexOf(book);
        art = await calculateNextArticle(idx >= 0 ? idx : 0);
      }
      const fullArt = syncArticleInputs(art);
      const bc = generateEan13FromArticle(fullArt);
      document.getElementById('barcode').value = bc;
      if (book) {
        book.article = fullArt;
        if (!book.formData) book.formData = {};
        book.formData.article = fullArt;
        book.formData.article_number = fullArt.replace(/\D/g, '').slice(-5);
        book.formData.barcode = bc;
        book.formData.template_mode = currentTemplateMode;
        book.formData.auto_package_adder = true;
      }
      autoCalcDimensions();
    }

    // -------------------------------------------------------------


// -------------------------------------------------------------
// СОХРАНЕНИЕ В EXCEL И VAULT, ПРЕДПРОСМОТР ТАБЛИЦЫ
// -------------------------------------------------------------
    // -------------------------------------------------------------
    // СОХРАНЕНИЕ В ИЗОЛИРОВАННЫЙ EXCEL
    // -------------------------------------------------------------
    async function saveBookToExcel() {
      // Сначала выполняем нечувствительную к регистру канонизацию полей
      snapToCanonical(document.getElementById('author_cover'), 'authors');
      snapToCanonical(document.getElementById('author'), 'authors');
      snapToCanonical(document.getElementById('publisher'), 'publishers');
      snapToCanonical(document.getElementById('brand'), 'brands');
      snapToCanonical(document.getElementById('series'), 'series');
      snapToCanonical(document.getElementById('translator'), 'translators');
      snapToCanonical(document.getElementById('illustrator'), 'illustrators');

      const title = document.getElementById('title').value.trim();
      if (!title) {
        alert('Пожалуйста, укажите название книги!');
        document.getElementById('title').focus();
        return;
      }

      const authorCover = document.getElementById('author_cover').value.trim();
      if (!authorCover) {
        alert('Пожалуйста, укажите автора на обложке (если автор отсутствует в книге, введите «не указан»)!');
        document.getElementById('author_cover').focus();
        return;
      }

      const author = document.getElementById('author').value.trim();
      if (!author) {
        alert('Пожалуйста, укажите официального автора книги (в паспортном формате «Фамилия Имя Отчество», либо «не указан»)!');
        document.getElementById('author').focus();
        return;
      }

      const paperType = document.getElementById('paper_type').value.trim();
      if (!paperType) {
        alert('Пожалуйста, выберите тип бумаги перед сохранением карточки!');
        document.getElementById('paper_type').focus();
        return;
      }

      const priceRaw = document.getElementById('price').value.trim();
      const priceVal = parseInt(priceRaw, 10);
      if (!priceVal || priceVal <= 0 || isNaN(priceVal)) {
        alert('Пожалуйста, укажите цену продажи книги (должна быть больше 0)!');
        document.getElementById('price').focus();
        return;
      }

      let article = document.getElementById('article').value.trim();
      if (!article) {
        await generateNewArticle();
        article = document.getElementById('article').value.trim() || 'DP-B-00001';
      }

      let barcodeVal = document.getElementById('barcode').value.trim();
      if (!barcodeVal || barcodeVal === 'генерирует озон' || !/^\d{12,13}$/.test(barcodeVal)) {
        barcodeVal = generateEan13FromArticle(article);
        document.getElementById('barcode').value = barcodeVal;
      }

      const btn = document.getElementById('saveBtn');
      btn.disabled = true;
      btn.innerHTML = '<span>⏳</span> <span>Запись в таблицу Ozon...</span>';

      const isbnVal = document.getElementById('isbn').value.trim();
      const publisherVal = document.getElementById('publisher') ? document.getElementById('publisher').value.trim() : '';

      const isPkgAdder = document.getElementById('autoPackageAdder')?.checked !== false;
      const rawWidth = parseInt(document.getElementById('width')?.value) || 130;
      const rawLength = parseInt(document.getElementById('length')?.value) || 205;
      const rawHeight = parseInt(document.getElementById('height')?.value) || 22;
      const rawWeight = parseInt(document.getElementById('weight')?.value) || 300;

      const pkgWidth = isPkgAdder ? (rawWidth + 10) : rawWidth;
      const pkgLength = isPkgAdder ? (rawLength + 10) : rawLength;
      const pkgHeight = isPkgAdder ? (rawHeight + 10) : rawHeight;
      const pkgWeight = isPkgAdder ? (rawWeight + 30) : rawWeight;
      const dimStr = `${pkgWidth}х${pkgLength}х${pkgHeight}`;

      const payload = {
        template_mode: currentTemplateMode,
        article: article,
        barcode: barcodeVal,
        isbn: (currentTemplateMode === 'pre2011') ? isbnVal : (isbnVal || '978-5-0000-0000-0'),
        title: title,
        original_title: (document.getElementById('original_title')?.value || '').trim(),
        series: document.getElementById('series').value.trim(),
        author_cover: authorCover,
        author: author,
        illustrator: document.getElementById('illustrator').value.trim(),
        translator: document.getElementById('translator').value.trim(),
        publisher: publisherVal,
        brand: document.getElementById('brand').value.trim() || 'Нет бренда',
        year: document.getElementById('year').value.trim(),
        pages: document.getElementById('pages').value.trim(),
        country: document.getElementById('country').value,
        cover_type: document.getElementById('cover_type').value,
        paper_type: paperType,
        genre: document.getElementById('genre').value,
        age_limit: document.getElementById('age_limit').value,
        target_audience: '',
        condition: document.getElementById('condition').value,
        defects: '',
        annotation: document.getElementById('annotation').value.trim(),
        hashtags: '',
        price: String(priceVal),
        old_price: document.getElementById('old_price').value.trim(),
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
        return { data: d, name: p.name || 'photo.jpg' };
      };

      const book = getActiveBook();
      const cbPayload = Array.isArray(book.slots.cover_back)
        ? book.slots.cover_back.map(extractPhotoPayload).filter(Boolean)
        : (book.slots.cover_back ? [extractPhotoPayload(book.slots.cover_back)].filter(Boolean) : []);

      const slots_photos = {
        cover_front: extractPhotoPayload(book.slots.cover_front),
        cover_back: cbPayload,
        info_pages: (book.slots.info_pages || []).map(extractPhotoPayload).filter(Boolean),
        illustrations: (book.slots.illustrations || []).map(extractPhotoPayload).filter(Boolean),
        mantra_defects: (book.slots.mantra_defects || []).map(extractPhotoPayload).filter(Boolean)
      };
      payload.slots_photos = slots_photos;

      const hasMantraDefects = Boolean(book.slots.mantra_defects && book.slots.mantra_defects.length > 0);
      payload.has_mantra_defects = hasMantraDefects;

      let finalAnt = cleanAnnotationText(document.getElementById('annotation').value);
      if (hasMantraDefects && finalAnt) {
        finalAnt = ANNOTATION_WARNING + '\n\n' + finalAnt;
      }
      payload.annotation = finalAnt;

      try {
        const res = await fetch('/api/save_book', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        if (result.success) {
          updateBooksCount();
          refreshPreviewTable(result.template_mode || currentTemplateMode);
          const photoCount = (result.saved_photos && result.saved_photos.length) || 0;
          const s3Badge = result.s3_enabled ? ' ☁️ [Yandex S3]' : '';
          const photoMsg = photoCount > 0 ? ` (в архив и S3 сохранено ${photoCount} фото${s3Badge})` : '';
          const fileName = result.file_name || ((result.template_mode === 'pre2011') ? `${getTodayStr()}_Печатная книга_до_2011.xlsx` : `${getTodayStr()}_Печатная книга_после_2011.xlsx`);
          const targetFolder = result.folder || ((result.template_mode === 'pre2011') ? 'ready_tables/1942-2010' : 'ready_tables/с_2011');
          const status = document.getElementById('formStatus');
          status.textContent = `✅ Книга "${result.title}" записана в ${targetFolder}/${fileName} (строка ${result.row})!${photoMsg}`;
          status.className = 'text-center text-xs text-emerald-400 font-semibold';
          showToast(`✅ Записано в <b>${targetFolder}/${fileName}</b> (строка ${result.row})${s3Badge}`);

          book.isSavedToExcel = true;
          loadCatalogReferences();
          renderBooksTabs();
          scheduleAutoSave();
          
          // Предлагаем перейти к следующей книге если есть неразобранные фото
          const unassigned = photoPool.filter(p => !p.assignedBookId).length;
          if (unassigned > 0) {
            setTimeout(() => {
              if (confirm(`Книга сохранена в шаблон (${templateLabel})! В пуле осталось ${unassigned} неразобранных фото. Создать карточку следующей книги?`)) {
                addNewBook();
              }
            }, 600);
          }
        }
      } catch (err) {
        alert('Ошибка записи: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>💾</span> <span>Записать книгу в Excel Ozon (Cmd + Enter)</span>';
      }
    }

    window.addEventListener('keydown', (e) => {
      const activeTag = (document.activeElement?.tagName || '').toLowerCase();
      const isInputFocused = ['input', 'textarea', 'select'].includes(activeTag);

      if (isStudioOpen) {
        // Esc: если активна рамка — снять рамку, иначе закрыть студию без сохранения
        if (e.key === 'Escape') {
          if (cropperInstance && cropperInstance.cropped) {
            resetCropToOriginal();
          } else {
            closePhotoStudio(false);
          }
          e.preventDefault();
          return;
        }

        // Cmd+S или Ctrl+S: мгновенное сохранение
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
          e.preventDefault();
          saveStudioChanges();
          return;
        }

        // Cmd+Shift+Z, Ctrl+Shift+Z или Cmd+Y, Ctrl+Y: шаг вперед (Redo)
        if ((e.metaKey || e.ctrlKey) && ((e.shiftKey && e.key.toLowerCase() === 'z') || e.key.toLowerCase() === 'y')) {
          e.preventDefault();
          redoStudioAction();
          return;
        }

        // Cmd+Z или Ctrl+Z (без Shift): отмена последнего действия (шаг назад в истории)
        if ((e.metaKey || e.ctrlKey) && !e.shiftKey && e.key.toLowerCase() === 'z') {
          e.preventDefault();
          undoStudioAction();
          return;
        }

        // Enter: сохранить все изменения студии
        if (e.key === 'Enter' && !e.ctrlKey && !e.metaKey) {
          e.preventDefault();
          saveStudioChanges();
          return;
        }

        // Горячие клавиши студии (активны, если оператор не пишет в текстовом поле)
        if (!isInputFocused || document.activeElement?.type === 'range') {
          // Стрелки влево/вправо или [ / ]: переход между фото книги
          if (e.key === 'ArrowRight' || e.key === ']') {
            e.preventDefault();
            navigateStudioPhoto(1);
            return;
          }
          if (e.key === 'ArrowLeft' || e.key === '[') {
            e.preventDefault();
            navigateStudioPhoto(-1);
            return;
          }

          // R / Shift+R: поворот на 90°
          if (e.key.toLowerCase() === 'r') {
            e.preventDefault();
            if (e.shiftKey) {
              rotateStudio(-90);
            } else {
              rotateStudio(90);
            }
            return;
          }

          // C: тогл режима обрезания (вход / выход)
          if (e.key.toLowerCase() === 'c') {
            e.preventDefault();
            toggleStudioCropMode();
            return;
          }

          // M или V: переключить на режим перемещения
          if (e.key.toLowerCase() === 'm' || e.key.toLowerCase() === 'v') {
            e.preventDefault();
            setStudioInteractionMode('move');
            showToast('✋ Режим перемещения кадра');
            return;
          }

          // W: пресет студийный белый фон Ozon
          if (e.key.toLowerCase() === 'w') {
            e.preventDefault();
            applyStudioPreset('studio_white');
            showToast('✨ Применен пресет: Студия Ozon (белый фон)');
            return;
          }

          // T: пресет резкий текст
          if (e.key.toLowerCase() === 't') {
            e.preventDefault();
            applyStudioPreset('sharp_text');
            showToast('📝 Применен пресет: Четкий текст');
            return;
          }

          // 0 или O: сброс фильтров в оригинал
          if (e.key === '0' || e.key.toLowerCase() === 'o') {
            e.preventDefault();
            applyStudioPreset('original');
            showToast('⚪ Фильтры сброшены в оригинал');
            return;
          }

          // + / - : плавный зум
          if (e.key === '+' || e.key === '=') {
            e.preventDefault();
            zoomStudio(0.15);
            return;
          }
          if (e.key === '-' || e.key === '_') {
            e.preventDefault();
            zoomStudio(-0.15);
            return;
          }
        }
        return;
      }

      // Глобальные горячие клавиши (когда студия закрыта)
      if (e.key === 'Escape') {
        closePhotoStudio(false);
        closeQrModal();
        closeKeyModal();
        closeCardModal();
        closeClearTableModal();
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
        saveBookToExcel();
      }
    });

    async function updateBooksCount() {
      try {
        const res = await fetch('/api/get_books');
        const data = await res.json();
        const preEl = document.getElementById('excelPre2011Count');
        const postEl = document.getElementById('excelPost2011Count');
        const preTab = document.getElementById('previewCountPre');
        const postTab = document.getElementById('previewCountPost');
        if (preEl) preEl.textContent = data.pre2011_count || 0;
        if (postEl) postEl.textContent = data.post2011_count || 0;
        if (preTab) preTab.textContent = data.pre2011_count || 0;
        if (postTab) postTab.textContent = data.post2011_count || 0;
      } catch (e) {}
    }

    function getTodayStr() {
      const d = new Date();
      const dd = String(d.getDate()).padStart(2, '0');
      const mm = String(d.getMonth() + 1).padStart(2, '0');
      const yyyy = d.getFullYear();
      return `${dd}.${mm}.${yyyy}`;
    }

    async function openReadyFolder() {
      try {
        const res = await fetch('/api/open_ready_folder');
        const data = await res.json();
        if (data.success) {
          showToast('📂 Папка с готовыми таблицами <b>ready_tables</b> открыта в Finder!');
        } else {
          alert('Ошибка открытия папки: ' + (data.error || ''));
        }
      } catch (e) {
        alert('Ошибка: ' + e.message);
      }
    }

    async function openFieldsGuide(docName = 'OZON_FIELDS_GUIDE.md') {
      try {
        const res = await fetch('/api/open_guide?name=' + encodeURIComponent(docName));
        const data = await res.json();
        if (data.success) {
          showToast(`📚 Памятка <b>${data.filename || docName}</b> открыта в режиме чтения!`);
        } else {
          alert('Ошибка открытия памятки: ' + (data.error || ''));
        }
      } catch (e) {
        alert('Ошибка: ' + e.message);
      }
    }

    async function openDocsFolder() {
      try {
        const res = await fetch('/api/open_docs_folder');
        const data = await res.json();
        if (data.success) {
          showToast('📂 Папка с памятками <b>docs</b> открыта в Finder!');
        } else {
          alert('Ошибка открытия папки docs: ' + (data.error || ''));
        }
      } catch (e) {
        alert('Ошибка: ' + e.message);
      }
    }

    async function openMemosModal() {
      const modal = document.getElementById('memosModal');
      if (!modal) return;
      modal.classList.remove('hidden');
      loadMemosList();
    }

    function closeMemosModal() {
      const modal = document.getElementById('memosModal');
      if (modal) modal.classList.add('hidden');
    }

    async function loadMemosList() {
      const container = document.getElementById('memosListContainer');
      if (!container) return;
      try {
        const res = await fetch('/api/get_memos');
        const data = await res.json();
        if (data.success && Array.isArray(data.memos)) {
          container.innerHTML = data.memos.map(m => `
            <div class="flex items-center justify-between p-3.5 rounded-2xl bg-slate-950/80 border border-slate-800 hover:border-slate-700 transition">
              <div class="flex items-start gap-3 min-w-0 pr-3">
                <span class="text-2xl shrink-0 mt-0.5">${m.icon || '📄'}</span>
                <div class="min-w-0">
                  <div class="flex items-center gap-2 flex-wrap">
                    <span class="text-xs font-bold text-white">${m.title}</span>
                    <span class="px-1.5 py-0.5 rounded text-[10px] font-mono border ${m.badge_color || 'bg-slate-800 text-slate-300 border-slate-700'}">${m.badge || m.category}</span>
                    <span class="text-[10px] text-slate-500 font-mono">${m.id} (${m.size_kb} KB)</span>
                  </div>
                  <p class="text-[11px] text-slate-400 mt-1 leading-snug">${m.desc}</p>
                </div>
              </div>
              <button type="button" onclick="openFieldsGuide('${m.id}')" class="shrink-0 px-3 py-1.5 rounded-xl bg-purple-900/60 hover:bg-purple-800/80 text-purple-200 text-xs font-semibold border border-purple-700/60 shadow-sm transition flex items-center gap-1.5">
                <span>📖</span>
                <span>Открыть на Mac</span>
              </button>
            </div>
          `).join('');
        }
      } catch (e) {
        console.warn('Ошибка загрузки памяток:', e);
      }
    }

    async function revealTableFile(mode) {
      try {
        const res = await fetch('/api/reveal_file?mode=' + mode);
        const data = await res.json();
        if (data.success) {
          showToast(`📂 Файл <b>${data.filename}</b> открыт в папке <b>${data.rel_folder || 'ready_tables'}</b>!`);
        } else {
          window.location.href = '/api/download_excel?mode=' + mode;
        }
      } catch (e) {
        window.location.href = '/api/download_excel?mode=' + mode;
      }
    }

    function showToast(msg) {
      let toast = document.getElementById('toastNotice');
      if (!toast) {
        toast = document.createElement('div');
        toast.id = 'toastNotice';
        toast.className = 'fixed bottom-5 right-5 z-50 px-4 py-2.5 rounded-xl bg-slate-900/95 border border-amber-500/50 text-white text-xs font-semibold shadow-2xl backdrop-blur-md transition-all duration-300 transform translate-y-0 opacity-100 flex items-center gap-2';
        document.body.appendChild(toast);
      }
      toast.innerHTML = msg;
      toast.classList.remove('opacity-0', 'translate-y-4');
      toast.classList.add('opacity-100', 'translate-y-0');
      clearTimeout(window._toastTimer);
      window._toastTimer = setTimeout(() => {
        toast.classList.remove('opacity-100', 'translate-y-0');
        toast.classList.add('opacity-0', 'translate-y-4');
      }, 3500);
    }

    // -------------------------------------------------------------
    // ПРЕДПРОСМОТР ТАБЛИЦЫ EXCEL OZON ВНИЗУ СТРАНИЦЫ
    // -------------------------------------------------------------
    let currentPreviewMode = 'pre2011';

    function switchPreviewTable(mode, shouldRefresh = true) {
      currentPreviewMode = (mode === 'post2011') ? 'post2011' : 'pre2011';
      const btnPre = document.getElementById('btnPreviewTabPre');
      const btnPost = document.getElementById('btnPreviewTabPost');
      const subtitle = document.getElementById('previewTableSubtitle');

      if (currentPreviewMode === 'pre2011') {
        if (btnPre) btnPre.className = 'px-3 py-1.5 text-xs font-semibold rounded-lg transition bg-amber-600 text-white shadow-sm flex items-center gap-1.5';
        if (btnPost) btnPost.className = 'px-3 py-1.5 text-xs font-medium rounded-lg transition text-slate-400 hover:text-white flex items-center gap-1.5';
        if (subtitle) subtitle.innerHTML = 'Готовая таблица в проекте: <code class="text-amber-400 bg-amber-950/40 px-1.5 py-0.5 rounded font-mono font-bold">ready_tables/1942-2010/' + getTodayStr() + '_Печатная книга_до_2011.xlsx</code> (81 колонка)';
      } else {
        if (btnPre) btnPre.className = 'px-3 py-1.5 text-xs font-medium rounded-lg transition text-slate-400 hover:text-white flex items-center gap-1.5';
        if (btnPost) btnPost.className = 'px-3 py-1.5 text-xs font-semibold rounded-lg transition bg-emerald-600 text-white shadow-sm flex items-center gap-1.5';
        if (subtitle) subtitle.innerHTML = 'Готовая таблица в проекте: <code class="text-emerald-400 bg-emerald-950/40 px-1.5 py-0.5 rounded font-mono font-bold">ready_tables/с_2011/' + getTodayStr() + '_Печатная книга_после_2011.xlsx</code> (86 колонок)';
      }

      if (shouldRefresh) {
        refreshPreviewTable(currentPreviewMode);
      }
    }

    function downloadCurrentPreviewExcel() {
      window.location.href = '/api/download_excel?mode=' + currentPreviewMode;
    }

    function downloadPhotosZip() {
      const book = getActiveBook();
      const art = (book && book.formData && book.formData.article) || (book && book.article) || (document.getElementById('article') ? document.getElementById('article').value.trim() : '');
      if (art) {
        showToast(`📦 Формирование ZIP-архива с фото для <b>${escapeHtml(art)}</b>...`);
        window.location.href = '/api/download_photos_zip?article=' + encodeURIComponent(art);
      } else {
        showToast('📦 Формирование общего ZIP-архива со всеми фото...');
        window.location.href = '/api/download_photos_zip?mode=all';
      }
    }

    function openClearTableModal() {
      const modal = document.getElementById('clearTableModal');
      if (!modal) return;

      const preCount = parseInt(document.getElementById('previewCountPre')?.textContent) || 0;
      const postCount = parseInt(document.getElementById('previewCountPost')?.textContent) || 0;

      const preBadge = document.getElementById('clearScopePreCountBadge');
      const postBadge = document.getElementById('clearScopePostCountBadge');
      const allBadge = document.getElementById('clearScopeAllCountBadge');
      if (preBadge) preBadge.textContent = `${preCount} книг`;
      if (postBadge) postBadge.textContent = `${postCount} книг`;
      if (allBadge) allBadge.textContent = `${preCount + postCount} книг`;

      const preDesc = document.getElementById('clearScopePreDesc');
      const postDesc = document.getElementById('clearScopePostDesc');
      if (preDesc) preDesc.textContent = `ready_tables/1942-2010/${getTodayStr()}_Печатная книга_до_2011.xlsx`;
      if (postDesc) postDesc.textContent = `ready_tables/с_2011/${getTodayStr()}_Печатная книга_после_2011.xlsx`;

      if (currentPreviewMode === 'post2011') {
        const rPost = document.getElementById('clearScopePost');
        if (rPost) rPost.checked = true;
      } else {
        const rPre = document.getElementById('clearScopePre');
        if (rPre) rPre.checked = true;
      }

      const check = document.getElementById('clearTableConfirmCheck');
      if (check) check.checked = false;
      onClearConfirmCheckChange();

      modal.classList.remove('hidden');
    }

    function closeClearTableModal() {
      const modal = document.getElementById('clearTableModal');
      if (modal) modal.classList.add('hidden');
    }

    function onClearConfirmCheckChange() {
      const check = document.getElementById('clearTableConfirmCheck');
      const btn = document.getElementById('btnClearTableExecute');
      if (!btn) return;

      if (check && check.checked) {
        btn.disabled = false;
        btn.className = 'px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-500 text-white text-xs font-bold transition flex items-center gap-1.5 shadow-lg shadow-rose-600/30 cursor-pointer';
      } else {
        btn.disabled = true;
        btn.className = 'px-4 py-2 rounded-xl bg-slate-800 text-slate-500 text-xs font-bold transition flex items-center gap-1.5 cursor-not-allowed';
      }
    }

    async function executeClearTable() {
      const check = document.getElementById('clearTableConfirmCheck');
      if (!check || !check.checked) return;

      const scopeEl = document.querySelector('input[name="clearScope"]:checked');
      const mode = scopeEl ? scopeEl.value : currentPreviewMode;

      const btn = document.getElementById('btnClearTableExecute');
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span>⏳ Очистка...</span>';
      }

      try {
        const res = await fetch('/api/clear_excel', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode: mode })
        });
        const data = await res.json();

        if (data.success) {
          closeClearTableModal();
          const modeTitle = mode === 'pre2011' ? 'до 2011 г.' : (mode === 'post2011' ? 'после 2011 г.' : 'обе таблицы');
          showToast(`🗑️ Таблица ${modeTitle} успешно очищена! Создан бэкап в ready_tables/backups/`);
          await updateBooksCount();
          await refreshPreviewTable(currentPreviewMode);
        } else {
          showToast(`❌ Ошибка очистки: ${data.error || 'Неизвестная ошибка'}`);
        }
      } catch (err) {
        showToast(`❌ Ошибка сети: ${err.message}`);
      } finally {
        if (btn) {
          btn.innerHTML = '<span>🗑️ Очистить таблицу</span>';
          onClearConfirmCheckChange();
        }
      }
    }

    function escapeHtml(str) {
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }

    async function refreshPreviewTable(mode = currentPreviewMode) {
      currentPreviewMode = (mode === 'post2011') ? 'post2011' : 'pre2011';
      const tbody = document.getElementById('excelPreviewTableBody');
      const summaryEl = document.getElementById('previewSummaryText');
      if (!tbody) return;

      try {
        const res = await fetch('/api/get_books?mode=' + currentPreviewMode);
        const data = await res.json();

        // Обновляем бейджи счетчиков
        const preEl = document.getElementById('excelPre2011Count');
        const postEl = document.getElementById('excelPost2011Count');
        const preTab = document.getElementById('previewCountPre');
        const postTab = document.getElementById('previewCountPost');
        if (preEl) preEl.textContent = data.pre2011_count || 0;
        if (postEl) postEl.textContent = data.post2011_count || 0;
        if (preTab) preTab.textContent = data.pre2011_count || 0;
        if (postTab) postTab.textContent = data.post2011_count || 0;

        const books = data.books || [];
        const modeLabel = (currentPreviewMode === 'pre2011') ? 'До 2011 г.' : 'После 2011 г.';

        if (summaryEl) {
          summaryEl.textContent = `Всего в таблице (${modeLabel}): ${books.length} ${books.length === 1 ? 'книга' : (books.length >= 2 && books.length <= 4 ? 'книги' : 'книг')}`;
        }

        if (books.length === 0) {
          tbody.innerHTML = `
            <tr>
              <td colspan="13" class="text-center py-10 text-slate-500">
                В этой таблице (${modeLabel}) пока нет сохраненных книг.<br>
                <span class="text-[11px] text-slate-600">Заполните форму выше и нажмите «Записать книгу в Excel».</span>
              </td>
            </tr>
          `;
          return;
        }

        tbody.innerHTML = books.map((b, idx) => {
          const rowNum = b.num || (idx + 1);
          const art = escapeHtml(b.article || '—');
          const title = escapeHtml(b.title || '—');
          const author = escapeHtml(b.author_cover || b.author || '—');
          const brandPub = escapeHtml((b.publisher ? b.publisher + ' / ' : '') + (b.brand || 'Нет бренда'));
          const yr = escapeHtml(b.year || '—');
          const price = b.price ? `${b.price} ₽` : '—';
          const cond = escapeHtml(b.condition || 'Очень хорошая');
          const country = escapeHtml(b.country || '—');
          const isbn = escapeHtml(b.isbn || '—');
          const dims = escapeHtml(b.dimensions || '—');
          const wt = b.weight ? `${b.weight} г` : '';
          const barcode = escapeHtml(b.barcode || '—');

          // Цвета бейджа сохранности
          let condBadge = 'bg-slate-800 text-slate-300 border-slate-700';
          if (cond === 'Отличная' || cond === 'Очень хорошая') {
            condBadge = 'bg-emerald-950/80 text-emerald-300 border-emerald-800/80';
          } else if (cond === 'Хорошая') {
            condBadge = 'bg-amber-950/80 text-amber-300 border-amber-800/80';
          } else if (cond.includes('Удовл')) {
            condBadge = 'bg-rose-950/80 text-rose-300 border-rose-800/80';
          }

          return `
            <tr class="hover:bg-slate-850/50 transition border-b border-slate-800/40">
              <td class="px-3 py-2.5 text-center font-mono text-slate-500">${rowNum}</td>
              <td class="px-3 py-2.5 font-mono font-semibold text-amber-300 whitespace-nowrap">
                <span class="bg-amber-950/60 px-2 py-0.5 rounded border border-amber-800/60 text-[11px]">${art}</span>
                ${b.photo_main ? `
                  <div class="mt-1 flex items-center gap-1 text-[10px] text-sky-400 font-sans font-medium" title="Главное фото + ${b.photos_additional ? b.photos_additional.split(' ').filter(Boolean).length : 0} доп. фото">
                    <span>📷 1+${b.photos_additional ? b.photos_additional.split(' ').filter(Boolean).length : 0} фото</span>
                  </div>
                ` : `
                  <div class="mt-1 text-[10px] text-slate-500 font-sans">нет фото</div>
                `}
              </td>
              <td class="px-3 py-2.5 font-semibold text-slate-100 max-w-xs truncate" title="${title}">${title}${b.original_title ? `<br><span class="text-[10px] text-amber-400/80 font-normal italic" title="Оригинал: ${escapeHtml(b.original_title)}">(${escapeHtml(b.original_title)})</span>` : ''}</td>
              <td class="px-3 py-2.5 text-slate-300 max-w-[160px] truncate" title="${author}">${author}</td>
              <td class="px-3 py-2.5 text-slate-400 max-w-[160px] truncate" title="${brandPub}">${brandPub}</td>
              <td class="px-3 py-2.5 text-center font-mono text-slate-300">${yr}</td>
              <td class="px-3 py-2.5 text-right font-mono font-bold text-emerald-400 whitespace-nowrap">${price}</td>
              <td class="px-3 py-2.5 text-center">
                <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold border ${condBadge}">${cond}</span>
              </td>
              <td class="px-3 py-2.5 text-center text-slate-300">${country}</td>
              <td class="px-3 py-2.5 font-mono text-slate-400 text-[11px] whitespace-nowrap">${isbn}</td>
              <td class="px-3 py-2.5 font-mono text-slate-400 text-[10px] whitespace-nowrap leading-tight">
                ${dims}${wt ? `<br><span class="text-slate-500">${wt}</span>` : ''}
              </td>
              <td class="px-3 py-2.5 font-mono text-slate-400 text-[11px] whitespace-nowrap">${barcode}</td>
              <td class="px-3 py-2.5 text-center whitespace-nowrap">
                <button type="button" onclick="deleteBookRow('${art}', '${title.replace(/'/g, "\\'")}')" class="p-1.5 rounded-lg bg-slate-900 hover:bg-rose-950/80 border border-slate-750 hover:border-rose-600/70 text-slate-400 hover:text-rose-300 transition text-xs flex items-center justify-center mx-auto" title="Удалить книгу ${art} из таблицы">
                  🗑️
                </button>
              </td>
            </tr>
          `;
        }).join('');

      } catch (err) {
        tbody.innerHTML = `
          <tr>
            <td colspan="13" class="text-center py-6 text-rose-400 text-xs">
              Ошибка загрузки предпросмотра таблицы: ${escapeHtml(err.message)}
            </td>
          </tr>
        `;
      }
    }

    async function deleteBookRow(article, title) {
      if (!article || article === '—') return;
      const cleanTitle = title || article;
      const confirmed = confirm(`Удалить строку книги «${cleanTitle}» (${article}) из таблицы Excel?\n\nОстальные строки будут автоматически перенумерованы, а перед удалением будет создан бэкап в ready_tables/backups/.`);
      if (!confirmed) return;

      try {
        const res = await fetch('/api/delete_book_row', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ article: article, mode: currentPreviewMode })
        });
        const data = await res.json();
        if (data.success) {
          showToast(`🗑️ Книга <b>${escapeHtml(article)}</b> удалена из таблицы Excel!`);
          await updateBooksCount();
          await refreshPreviewTable(currentPreviewMode);
        } else {
          alert('Ошибка при удалении книги: ' + (data.error || 'Неизвестная ошибка'));
        }
      } catch (err) {
        alert('Ошибка сети: ' + err.message);
      }
    }

    // -------------------------------------------------------------


// -------------------------------------------------------------
// КЛЮЧИ GEMINI, ИНТЕГРАЦИЯ С OZON И ИНИЦИАЛИЗАЦИЯ
// -------------------------------------------------------------
    // Управление ключом Gemini с синхронизацией между файлом настроек и браузером
    async function loadSavedKey() {
      if (!currentApiKey && typeof localStorage !== 'undefined') {
        currentApiKey = localStorage.getItem('gemini_api_key') || '';
      }
      updateKeyUi();

      try {
        const res = await fetch('/api/get_key');
        const data = await res.json();
        if (data.key && data.key.trim()) {
          currentApiKey = data.key.trim();
          if (typeof localStorage !== 'undefined') {
            localStorage.setItem('gemini_api_key', currentApiKey);
          }
        } else if (currentApiKey) {
          // Если на бэкенде ключ пустой, но есть в браузере, передаем его на сохранение в файл
          fetch('/api/save_key', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ key: currentApiKey })
          }).catch(() => {});
        }
        updateKeyUi();
      } catch (e) {
        updateKeyUi();
      }
    }

    function updateKeyUi() {
      const dot = document.getElementById('keyDot');
      const label = document.getElementById('keyLabel');
      if (!dot || !label) return;
      if (currentApiKey) {
        dot.className = 'w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]';
        label.textContent = 'Ключ Gemini подключен';
        label.title = 'Ключ активен: ' + currentApiKey.substring(0, 6) + '...' + currentApiKey.slice(-4);
      } else {
        dot.className = 'w-2 h-2 rounded-full bg-amber-400 animate-pulse';
        label.textContent = 'Ввести API ключ';
        label.title = 'API ключ не настроен';
      }
    }

    function openKeyModal() {
      document.getElementById('apiKeyInput').value = currentApiKey;
      document.getElementById('keyModal').classList.remove('hidden');
    }
    function closeKeyModal() { document.getElementById('keyModal').classList.add('hidden'); }
    function openCardModal() {
      document.getElementById('cardModal').classList.remove('hidden');
    }
    function closeCardModal() {
      document.getElementById('cardModal').classList.add('hidden');
    }

    async function saveKeyFromModal() {
      const val = document.getElementById('apiKeyInput').value.trim();
      currentApiKey = val;
      if (typeof localStorage !== 'undefined') {
        if (val) {
          localStorage.setItem('gemini_api_key', val);
        } else {
          localStorage.removeItem('gemini_api_key');
        }
      }
      updateKeyUi();
      await fetch('/api/save_key', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ key: val })
      });
      closeKeyModal();
    }

    // =========================================================================
    // УПРАВЛЕНИЕ ИНТЕГРАЦИЕЙ OZON SELLER API
    // =========================================================================
    let ozonImportInterval = null;

    async function loadOzonStatus() {
      try {
        const res = await fetch('/api/ozon/status');
        const data = await res.json();
        updateOzonUI(data);
        return data;
      } catch (e) {
        console.error('Ошибка проверки Ozon API:', e);
        updateOzonUI({ configured: false, success: false, message: 'Сервер недоступен' });
      }
    }

    function updateOzonUI(data) {
      const dot = document.getElementById('ozonDot');
      const label = document.getElementById('ozonLabel');
      const badge = document.getElementById('ozonStatusBadge');
      const cidVal = document.getElementById('ozonClientIdVal');
      const totVal = document.getElementById('ozonTotalProductsVal');
      const nextArtVal = document.getElementById('ozonNextArticleVal');

      const isOk = data && data.configured && data.success;
      const isConfigured = data && data.configured;

      if (dot) {
        if (isOk) {
          dot.className = 'w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]';
        } else if (isConfigured) {
          dot.className = 'w-2 h-2 rounded-full bg-rose-500 animate-pulse';
        } else {
          dot.className = 'w-2 h-2 rounded-full bg-amber-400 animate-pulse';
        }
      }

      if (label) {
        if (isOk) {
          label.textContent = `Ozon API (${data.total_products || 0})`;
          label.title = `Ozon подключен: ${data.total_products || 0} товаров`;
        } else if (isConfigured) {
          label.textContent = 'Ozon: Ошибка';
          label.title = data.message || 'Ошибка подключения';
        } else {
          label.textContent = 'Ozon API';
          label.title = 'Ozon Seller API не настроен';
        }
      }

      if (badge) {
        if (isOk) {
          badge.className = 'px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-emerald-950 text-emerald-400 border border-emerald-800';
          badge.textContent = '🟢 Активно (роль: Товары)';
        } else if (isConfigured) {
          badge.className = 'px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-rose-950 text-rose-400 border border-rose-800';
          badge.textContent = '🔴 Ошибка: ' + (data.message || 'нет связи');
        } else {
          badge.className = 'px-2.5 py-0.5 rounded-full text-[11px] font-mono font-bold bg-slate-800 text-slate-400 border border-slate-700';
          badge.textContent = '⚪ Не настроен';
        }
      }

      if (cidVal) {
        cidVal.textContent = data.client_id || '—';
      }
      if (totVal) {
        totVal.textContent = (data.total_products !== undefined && data.total_products !== null) ? `${data.total_products} шт.` : '—';
      }
      if (nextArtVal) {
        nextArtVal.textContent = data.next_article || '—';
      }
    }

    function openOzonModal() {
      const modal = document.getElementById('ozonModal');
      if (modal) modal.classList.remove('hidden');
      loadOzonStatus();
      checkOzonImportStatus();
    }

    function closeOzonModal() {
      const modal = document.getElementById('ozonModal');
      if (modal) modal.classList.add('hidden');
    }

    async function refreshOzonStatus() {
      const data = await loadOzonStatus();
      if (data && data.success) {
        alert(`✅ Подключение к Ozon Seller API активно!\nТоваров в магазине: ${data.total_products || 0}\nСледующий артикул: ${data.next_article || '—'}`);
      } else {
        alert(`⚠️ Ozon API: ${data ? data.message : 'Ошибка связи'}`);
      }
    }

    async function saveOzonKeysFromModal() {
      const clientId = document.getElementById('ozonClientIdInput')?.value.trim();
      const apiKey = document.getElementById('ozonApiKeyInput')?.value.trim();

      if (!clientId || !apiKey) {
        alert('⚠️ Пожалуйста, укажите Client-Id и Api-Key магазина Ozon.');
        return;
      }

      try {
        const res = await fetch('/api/ozon/save_keys', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ client_id: clientId, api_key: apiKey })
        });
        const data = await res.json();
        if (data.success) {
          alert('✅ Ключи Ozon сохранены! Проверяем подключение...');
          await loadOzonStatus();
        } else {
          alert('❌ Ошибка сохранения ключей: ' + (data.error || 'Неизвестная ошибка'));
        }
      } catch (e) {
        alert('❌ Сбой запроса сохранения ключей Ozon: ' + e.message);
      }
    }

    async function checkOzonImportStatus() {
      try {
        const res = await fetch('/api/ozon/import_status');
        const data = await res.json();
        if (data.success && data.status) {
          renderOzonImportProgress(data.status);
          if (data.status.running && !ozonImportInterval) {
            pollOzonImportProgress();
          }
        }
      } catch (e) {}
    }

    function renderOzonImportProgress(st) {
      const box = document.getElementById('ozonImportProgressBox');
      const text = document.getElementById('ozonImportProgressText');
      const pctEl = document.getElementById('ozonImportProgressPct');
      const bar = document.getElementById('ozonImportProgressBar');
      const btn = document.getElementById('btnStartOzonImport');
      const btnText = document.getElementById('btnStartOzonImportText');

      if (!box) return;

      if (st.running || st.progress > 0 || st.done || st.error) {
        box.classList.remove('hidden');
      }

      const total = st.total || 0;
      const cur = st.progress || 0;
      const pct = total > 0 ? Math.min(100, Math.round((cur / total) * 100)) : (st.running ? 5 : 0);

      if (pctEl) pctEl.textContent = `${pct}%`;
      if (bar) bar.style.width = `${pct}%`;

      if (st.running) {
        if (btn) btn.disabled = true;
        if (btnText) btnText.textContent = '⏳ Идет синхронизация...';
        if (text) text.textContent = `Загружено ${cur} из ${total} (новых: ${st.imported || 0}, обновлено: ${st.updated || 0})`;
      } else if (st.done) {
        if (btn) btn.disabled = false;
        if (btnText) btnText.textContent = '📥 Запустить повторную синхронизацию';
        if (text) text.textContent = `✅ Успешно синхронизировано ${cur} карточек! (Новых: ${st.imported || 0}, в базе: ${st.updated || 0})`;
      } else if (st.error) {
        if (btn) btn.disabled = false;
        if (btnText) btnText.textContent = '📥 Попробовать снова';
        if (text) text.textContent = `❌ Ошибка импорта: ${st.error}`;
      }
    }

    async function startOzonCatalogImport() {
      if (!confirm('Запустить полную синхронизацию карточек из Ozon в локальную базу SQLite?\nЭто обновит каталог, цены, фото и рассчитает актуальный следующий артикул.')) {
        return;
      }

      const btn = document.getElementById('btnStartOzonImport');
      const btnText = document.getElementById('btnStartOzonImportText');
      if (btn) btn.disabled = true;
      if (btnText) btnText.textContent = 'Запуск импорта...';

      try {
        const res = await fetch('/api/ozon/start_import', { method: 'POST' });
        const data = await res.json();
        if (data.success) {
          const box = document.getElementById('ozonImportProgressBox');
          if (box) box.classList.remove('hidden');
          pollOzonImportProgress();
        } else {
          alert('⚠️ Ошибка: ' + (data.error || 'Не удалось запустить импорт'));
          if (btn) btn.disabled = false;
          if (btnText) btnText.textContent = 'Запустить импорт каталога Ozon';
        }
      } catch (e) {
        alert('❌ Ошибка запуска импорта: ' + e.message);
        if (btn) btn.disabled = false;
        if (btnText) btnText.textContent = 'Запустить импорт каталога Ozon';
      }
    }

    function pollOzonImportProgress() {
      if (ozonImportInterval) clearInterval(ozonImportInterval);

      ozonImportInterval = setInterval(async () => {
        try {
          const res = await fetch('/api/ozon/import_status');
          const data = await res.json();
          if (data.success && data.status) {
            renderOzonImportProgress(data.status);
            if (!data.status.running) {
              clearInterval(ozonImportInterval);
              ozonImportInterval = null;
              loadOzonStatus();
              updateBooksCount();
            }
          }
        } catch (e) {
          console.error('Ошибка опроса прогресса импорта:', e);
        }
      }, 1200);
    }
