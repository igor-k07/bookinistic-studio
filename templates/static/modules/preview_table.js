/**
 * preview_table.js: Предпросмотр готовых таблиц Excel (до 2011 / после 2011),
 * скачивание файлов, выгрузка фото в ZIP, удаление строк и очистка таблиц.
 */

(function (window) {
  'use strict';

  let currentPreviewMode = 'pre2011';

  function getTodayStr() {
    const d = new Date();
    const dd = String(d.getDate()).padStart(2, '0');
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const yyyy = d.getFullYear();
    return `${dd}.${mm}.${yyyy}`;
  }

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
    } catch (e) {
      console.warn('Ошибка обновления счетчиков книг:', e);
    }
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
    const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
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
      const data = window.ApiClient
        ? await window.ApiClient.clearExcel(mode)
        : await fetch('/api/clear_excel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode })
          }).then(r => r.json());

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
              <div class="flex items-center justify-center gap-1">
                <button type="button" onclick="reopenBook('${art}')" class="p-1.5 rounded-lg bg-amber-950/60 hover:bg-amber-600 border border-amber-700/60 hover:border-amber-400 text-amber-300 hover:text-black transition text-xs flex items-center justify-center" title="✏️ Открыть книгу ${art} для редактирования фото и полей">
                  ✏️
                </button>
                <button type="button" onclick="updateOzonPhotos('${art}', '${b.photo_main || ''}', '${b.photos_additional || ''}')" class="p-1.5 rounded-lg bg-sky-950/60 hover:bg-sky-600 border border-sky-700/60 hover:border-sky-400 text-sky-300 hover:text-white transition text-xs flex items-center justify-center" title="🔄 Точечно обновить фото товара ${art} на Ozon">
                  🔄
                </button>
                <button type="button" onclick="deleteBookRow('${art}', '${title.replace(/'/g, "\\'")}')" class="p-1.5 rounded-lg bg-slate-900 hover:bg-rose-950/80 border border-slate-750 hover:border-rose-600/70 text-slate-400 hover:text-rose-300 transition text-xs flex items-center justify-center" title="Удалить книгу ${art} из таблицы">
                  🗑️
                </button>
              </div>
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
      const data = window.ApiClient
        ? await window.ApiClient.deleteBookRow(article, currentPreviewMode)
        : await fetch('/api/delete_book_row', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ article, mode: currentPreviewMode })
          }).then(r => r.json());

      if (data.success) {
        showToast(`🗑️ Книга <b>${escapeHtml(article)}</b> удалена из таблицы Excel!`);
        // Если удаленная книга была открыта во вкладке сессии, снимаем флаг isSavedToExcel
        const sessionBook = (window.booksSession || []).find(b => {
          const bArt = String(b.article || (b.formData && b.formData.article) || '').trim().toUpperCase();
          return bArt === String(article).trim().toUpperCase();
        });
        if (sessionBook) {
          sessionBook.isSavedToExcel = false;
          if (sessionBook.id === window.activeBookId) {
            if (typeof window.updateCardModeBanner === 'function') window.updateCardModeBanner();
          }
          if (typeof window.scheduleAutoSave === 'function') window.scheduleAutoSave();
        }
        await updateBooksCount();
        await refreshPreviewTable(currentPreviewMode);
      } else {
        alert('Ошибка при удалении книги: ' + (data.error || 'Неизвестная ошибка'));
      }
    } catch (err) {
      alert('Ошибка сети: ' + err.message);
    }
  }

  async function reopenBook(article) {
    if (!article || article === '—') return;
    const cleanArt = String(article).trim().toUpperCase();

    // 1. Сначала проверяем: возможно эта книга УЖЕ открыта в одной из вкладок текущей сессии?
    const existingIndex = (window.booksSession || []).findIndex(b => {
      const bArt = String(b.article || (b.formData && b.formData.article) || '').trim().toUpperCase();
      return bArt === cleanArt;
    });

    if (existingIndex >= 0) {
      // Книга уже есть во вкладках — просто сохраняем текущую форму и переключаемся на нужную вкладку!
      if (typeof window.saveCurrentFormToActiveBook === 'function') {
        window.saveCurrentFormToActiveBook();
      }
      const existingBook = window.booksSession[existingIndex];
      existingBook.isEditMode = true;
      existingBook.isReopened = true;
      existingBook.isSavedToExcel = true;
      window.activeBookId = existingBook.id;

      if (typeof window.renderBooksTabs === 'function') window.renderBooksTabs();
      if (typeof window.restoreFormFromActiveBook === 'function') window.restoreFormFromActiveBook();
      if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
      if (typeof window.updateCardModeBanner === 'function') window.updateCardModeBanner();
      if (typeof window.renderPool === 'function') window.renderPool();
      if (typeof window.scheduleAutoSave === 'function') window.scheduleAutoSave();

      const studioCard = document.getElementById('bookStudioCard') || document.getElementById('slot_cover_front');
      if (studioCard) studioCard.scrollIntoView({ behavior: 'smooth', block: 'start' });

      if (typeof showToast === 'function') {
        showToast(`✏️ Книга <b>${escapeHtml(article)}</b> уже открыта во вкладке #${existingBook.id}! Переключились на неё.`);
      }
      return;
    }

    // 2. Книга ещё не открыта в текущей сессии — запрашиваем её из хранилища
    if (typeof showToast === 'function') {
      showToast(`⏳ Загрузка книги <b>${escapeHtml(article)}</b> из хранилища...`);
    }

    try {
      const res = await fetch('/api/books/reopen', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ article })
      });
      const data = await res.json();
      if (!data.success) {
        alert('Ошибка открытия книги: ' + (data.error || 'Неизвестная ошибка'));
        return;
      }

      const book = data.book;

      // 3. Сохраняем текущую форму перед переключением
      if (typeof window.saveCurrentFormToActiveBook === 'function') {
        window.saveCurrentFormToActiveBook();
      }

      // 4. Проверяем, свободна ли текущая активная вкладка (совершенно чистый черновик без фото и полей)
      const currentActive = typeof getActiveBook === 'function' ? getActiveBook() : null;
      const isCurrentEmpty = currentActive && !currentActive.isEditMode && !currentActive.isReopened && !currentActive.isSavedToExcel &&
        (!currentActive.slots || (!currentActive.slots.cover_front && (!currentActive.slots.cover_back || currentActive.slots.cover_back.length === 0) &&
        (!currentActive.slots.info_pages || currentActive.slots.info_pages.length === 0) &&
        (!currentActive.slots.illustrations || currentActive.slots.illustrations.length === 0) &&
        (!currentActive.slots.mantra_defects || currentActive.slots.mantra_defects.length === 0))) &&
        (!currentActive.formData || !currentActive.formData.title || currentActive.formData.title.startsWith('Книга #') || currentActive.formData.title === 'Без названия');

      let targetBook;
      if (isCurrentEmpty) {
        // Текущая вкладка пустая — используем её
        targetBook = currentActive;
        targetBook.article = book.article;
        targetBook.title = book.title;
        targetBook.slots = book.slots;
        targetBook.formData = book.formData || {};
        targetBook.isReopened = true;
        targetBook.isEditMode = true;
        targetBook.isSavedToExcel = true;
      } else {
        // Создаем НОВУЮ отдельную вкладку книги в сессии, НЕ затирая другие карточки
        const books = window.booksSession || [];
        const nextId = books.length > 0 ? Math.max(...books.map(x => x.id)) + 1 : 1;
        targetBook = {
          id: nextId,
          article: book.article,
          title: book.title || `Книга #${nextId}`,
          slots: book.slots,
          formData: book.formData || {},
          isReopened: true,
          isEditMode: true,
          isSavedToExcel: true,
        };
        books.push(targetBook);
        window.activeBookId = nextId;
      }

      // Фото книги находятся непосредственно в targetBook.slots.
      // Не дублируем их в общий пул неразобранных фото (photoPool предназначен только для входящих кадров с телефона).
      if (book.slots && window.photoPool) {
        Object.entries(book.slots).forEach(([slotKey, slotVal]) => {
          const items = Array.isArray(slotVal) ? slotVal : (slotVal ? [slotVal] : []);
          items.forEach(p => {
            if (p && p.id) {
              p.assignedBookId = targetBook.id;
              p.assignedSlot = slotKey;
              const exIdx = window.photoPool.findIndex(x => x.id === p.id);
              if (exIdx >= 0) {
                window.photoPool[exIdx].assignedBookId = targetBook.id;
                window.photoPool[exIdx].assignedSlot = slotKey;
              }
            }
          });
        });
      }

      if (typeof window.renderBooksTabs === 'function') window.renderBooksTabs();
      if (typeof window.restoreFormFromActiveBook === 'function') window.restoreFormFromActiveBook();
      if (typeof window.renderActiveBookSlots === 'function') window.renderActiveBookSlots();
      if (typeof window.updateCardModeBanner === 'function') window.updateCardModeBanner();
      if (typeof window.renderPool === 'function') window.renderPool();
      if (typeof window.scheduleAutoSave === 'function') window.scheduleAutoSave();

      const studioCard = document.getElementById('bookStudioCard') || document.getElementById('slot_cover_front');
      if (studioCard) {
        studioCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }

      if (typeof showToast === 'function') {
        showToast(`✏️ Книга <b>${escapeHtml(article)}</b> открыта в отдельной вкладке! Можно редактировать фото и поля.`);
      }
    } catch (err) {
      alert('Ошибка сети: ' + err.message);
    }
  }

  async function updateOzonPhotos(article, mainPhoto, addPhotos) {
    if (!article || article === '—') return;
    const confirmed = confirm(`Отправить обновленные фотографии товара ${article} напрямую в Ozon Seller API?`);
    if (!confirmed) return;

    if (typeof showToast === 'function') {
      showToast(`⏳ Обновление фото товара <b>${escapeHtml(article)}</b> на Ozon...`);
    }
    try {
      const res = await fetch('/api/ozon/update_pictures', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          article: article,
          primary_image: mainPhoto,
          add_photo_urls: addPhotos
        })
      });
      const data = await res.json();
      if (data.success) {
        const taskIdStr = data.task_id ? ` (Задача #${data.task_id})` : '';
        if (typeof showToast === 'function') {
          showToast(`✅ Фотографии товара <b>${escapeHtml(article)}</b> успешно приняты Ozon!${taskIdStr}`);
        } else {
          alert(`✅ Фотографии товара ${article} успешно отправлены в Ozon Seller API!${taskIdStr}`);
        }
      } else {
        alert('Ошибка обновления на Ozon: ' + (data.error || 'Проверьте API ключи Ozon'));
      }
    } catch (e) {
      alert('Ошибка сети: ' + e.message);
    }
  }

  async function updateActiveBookOzonPictures() {
    const book = typeof window.getActiveBook === 'function' ? window.getActiveBook() : null;
    const article = (book && book.article) || document.getElementById('article')?.value?.trim();
    if (!article || article === '—') {
      alert('Сначала укажите артикул книги или откройте её из базы через кнопку «📥 Загрузить» или поиск!');
      return;
    }

    const title = (book && book.title) || document.getElementById('title')?.value?.trim() || 'Книга';
    const slots = book ? book.slots : null;

    if (!slots || !slots.cover_front) {
      alert(`Для обновления карточки товара ${article} на Ozon обязательно должно быть заполнено главное фото (обложка) в слоте 1!`);
      return;
    }

    const confirmed = confirm(`Отправить обновленные фотографии товара ${article} («${title}») напрямую в Ozon Seller API?\n\nМаркетплейс обновит витрину карточки без перезаливки Excel таблицы.`);
    if (!confirmed) return;

    if (typeof showToast === 'function') {
      showToast(`⏳ Подготовка и отправка фото товара <b>${escapeHtml(article)}</b> в Ozon...`);
    }

    try {
      const res = await fetch('/api/ozon/update_pictures', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          article: article,
          title: title,
          slots_photos: slots,
        })
      });
      const data = await res.json();
      if (data.success) {
        const taskIdStr = data.task_id ? ` (Задача #${data.task_id})` : '';
        if (typeof showToast === 'function') {
          showToast(`✅ Фотографии товара <b>${escapeHtml(article)}</b> успешно приняты Ozon!${taskIdStr} Модерация и обновление витрины займут 1-2 минуты.`);
        } else {
          alert(`✅ Фотографии товара ${article} успешно отправлены в Ozon Seller API!${taskIdStr}`);
        }
      } else {
        alert('Ошибка обновления на Ozon: ' + (data.error || 'Проверьте API ключи Ozon'));
      }
    } catch (e) {
      alert('Ошибка сети при отправке на Ozon: ' + e.message);
    }
  }

  async function smartSaveActiveBook() {
    if (typeof window.saveBookToExcel === 'function') {
      return await window.saveBookToExcel();
    }
    const article = (book && book.article) || document.getElementById('article')?.value?.trim();
    if (!article || article === '—') {
      alert('Сначала укажите артикул книги или откройте её из базы через кнопку «📥 Загрузить» или поиск!');
      return;
    }

    const title = (book && book.title) || document.getElementById('title')?.value?.trim() || 'Книга';
    const slots = book ? book.slots : null;

    // Собираем актуальные данные полей формы
    const formData = {};
    const fieldIds = [
      'article', 'title', 'original_title', 'author', 'author_cover',
      'publisher', 'brand', 'year', 'pages', 'isbn', 'isbn_100_percent_on_photo',
      'barcode', 'cover_type', 'condition', 'genre', 'paper_type', 'age_limit',
      'annotation', 'translator', 'illustrator', 'price', 'old_price',
      'width', 'length', 'height', 'weight',
      'width_mm', 'length_mm', 'height_mm', 'weight_g',
      'width_package', 'length_package', 'height_package', 'weight_package',
      'dimensions', 'autoPackageAdder', 'auto_package_adder',
      'book_format_code', 'template_mode'
    ];
    for (const fid of fieldIds) {
      const el = document.getElementById(fid);
      if (el) {
        formData[fid] = (el.type === 'checkbox') ? el.checked : el.value;
      }
    }
    if (formData.width) formData.width_mm = formData.width;
    if (formData.length) formData.length_mm = formData.length;
    if (formData.height) formData.height_mm = formData.height;
    if (formData.weight) formData.weight_g = formData.weight;
    if (formData.autoPackageAdder !== undefined) formData.auto_package_adder = formData.autoPackageAdder;
    const rawY = parseInt(formData.year, 10);
    if (!isNaN(rawY) && rawY > 1000 && rawY < 2100) {
      formData.template_mode = (rawY <= 2011) ? 'pre2011' : 'post2011';
    } else {
      formData.template_mode = window.currentTemplateMode || 'pre2011';
    }

    if (formData.author_cover && ['автор не указан', 'нет автора', 'неизвестен', 'нет', 'отсутствует'].includes(formData.author_cover.toLowerCase())) {
      formData.author_cover = 'не указан';
    }
    if (formData.author && ['автор не указан', 'нет автора', 'неизвестен', 'нет', 'отсутствует'].includes(formData.author.toLowerCase())) {
      formData.author = 'не указан';
    }
    if (formData.publisher && typeof window.cleanPublisherName === 'function') {
      formData.publisher = window.cleanPublisherName(formData.publisher);
    }

    const confirmed = confirm(
      `Сохранить изменения и синхронизировать с Ozon товар ${article} («${title}»)?\n\n` +
      `• Отредактированные фото загрузятся в S3 и витрину Ozon\n` +
      `• Измененные текст, цена и параметры обновятся в Excel, базе и Ozon Seller API`
    );
    if (!confirmed) return;

    if (typeof showToast === 'function') {
      showToast(`⏳ Синхронизация книги <b>${escapeHtml(article)}</b> с Excel, Ozon и облаком S3...`);
    }

    const saveBtn = document.getElementById('saveBtn');
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.innerHTML = '<span>⏳</span> <span>Сохранение в Excel, Ozon и БД...</span>';
    }

    try {
      const res = await fetch('/api/books/smart_save', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          article: article,
          title: title,
          formData: formData,
          slots_photos: slots,
        })
      });
      const data = await res.json();
      if (data.success) {
        const picTask = data.pictures_task_id ? ` фото (#${data.pictures_task_id})` : '';
        const prodTask = data.product_task_id ? ` карточка (#${data.product_task_id})` : '';
        const tasksSummary = (picTask || prodTask) ? ` Задачи Ozon:${picTask}${prodTask}.` : '';

        if (typeof showToast === 'function') {
          showToast(`✅ Книга <b>${escapeHtml(article)}</b> успешно сохранена и синхронизирована с Ozon!${tasksSummary}`);
        } else {
          alert(`✅ Книга ${article} успешно сохранена и синхронизирована с Ozon!${tasksSummary}`);
        }
        if (typeof refreshPreviewTable === 'function') {
          refreshPreviewTable();
        }
        if (typeof window.updateCardModeBanner === 'function') {
          window.updateCardModeBanner();
        }
      } else {
        alert('Ошибка сохранения: ' + (data.error || 'Проверьте соединение с Ozon'));
      }
    } catch (e) {
      alert('Ошибка сети: ' + e.message);
    } finally {
      if (typeof window.updateCardModeBanner === 'function') {
        window.updateCardModeBanner();
      } else if (saveBtn) {
        saveBtn.disabled = false;
      }
    }
  }

  let catalogSearchTimeout = null;

  function openCatalogSearchModal() {
    const m = document.getElementById('catalogSearchModal');
    if (m) m.classList.remove('hidden');
    const inp = document.getElementById('catalogSearchInput');
    if (inp) {
      inp.focus();
      searchCatalogBooks(inp.value || '');
    }
  }

  function closeCatalogSearchModal() {
    const m = document.getElementById('catalogSearchModal');
    if (m) m.classList.add('hidden');
  }

  function onCatalogSearchInput(query) {
    clearTimeout(catalogSearchTimeout);
    catalogSearchTimeout = setTimeout(() => {
      searchCatalogBooks(query);
    }, 250);
  }

  async function searchCatalogBooks(query) {
    const container = document.getElementById('catalogSearchResults');
    if (!container) return;
    container.innerHTML = '<div class="text-center py-10 text-xs text-slate-400"><span>⏳ Поиск в базе catalog.db...</span></div>';

    try {
      const q = encodeURIComponent((query || '').trim());
      const res = await fetch(`/api/get_db_catalog?search=${q}`);
      const data = await res.json();
      const books = data.books || [];
      const summary = document.getElementById('catalogSearchSummary');
      if (summary) summary.textContent = `Найдено: ${books.length} книг в базе`;

      if (books.length === 0) {
        container.innerHTML = '<div class="text-center py-12 text-slate-500 text-xs">Ничего не найдено по этому запросу.</div>';
        return;
      }

      container.innerHTML = books.slice(0, 50).map(b => {
        const art = escapeHtml(b.article || '');
        const title = escapeHtml(b.title || 'Без названия');
        const author = escapeHtml(b.author || b.author_cover || '—');
        const yr = escapeHtml(b.year ? String(b.year) : '');
        const price = b.price ? `${b.price} ₽` : '';
        const photo = b.main_photo_url || b.photo_main || '';

        return `
          <div class="flex items-center justify-between gap-3 p-2.5 rounded-xl bg-slate-900/80 hover:bg-slate-850 border border-slate-800 transition">
            <div class="flex items-center gap-3 min-w-0">
              <div class="w-12 h-16 rounded-lg bg-slate-950 border border-slate-800 overflow-hidden shrink-0 flex items-center justify-center">
                ${photo ? `<img src="${photo}" class="w-full h-full object-cover" onerror="this.parentElement.innerHTML='<span class=\\'text-xs text-slate-600\\'>📷</span>'">` : '<span class="text-xs text-slate-600">📷</span>'}
              </div>
              <div class="min-w-0">
                <div class="flex items-center gap-2 mb-0.5">
                  <span class="px-2 py-0.5 rounded font-mono font-bold text-[11px] bg-amber-950/80 text-amber-300 border border-amber-800/80">${art}</span>
                  ${yr ? `<span class="text-slate-400 text-[11px] font-mono">${yr} г.</span>` : ''}
                  ${price ? `<span class="text-emerald-400 text-[11px] font-mono font-bold">${price}</span>` : ''}
                </div>
                <div class="text-xs font-semibold text-white truncate max-w-md" title="${title}">${title}</div>
                <div class="text-[11px] text-slate-400 truncate max-w-sm">${author}</div>
              </div>
            </div>
            <button type="button" onclick="closeCatalogSearchModal(); reopenBook('${art}');" class="px-3 py-1.5 rounded-xl bg-amber-600 hover:bg-amber-500 text-black font-bold text-xs shadow-md transition flex items-center gap-1 shrink-0 cursor-pointer">
              <span>✏️ Открыть</span>
            </button>
          </div>
        `;
      }).join('');
    } catch(e) {
      container.innerHTML = `<div class="text-center py-6 text-xs text-rose-400">Ошибка: ${escapeHtml(e.message)}</div>`;
    }
  }

  let smartSyncPollTimer = null;

  async function startSmartS3Sync() {
    const btn = document.getElementById('btnSmartS3Sync');
    if (btn) btn.disabled = true;

    try {
      const res = await fetch('/api/sync/smart_s3', { method: 'POST' });
      const data = await res.json();
      if (!data.success) {
        alert(data.error || 'Ошибка запуска синхронизации');
        if (btn) btn.disabled = false;
        return;
      }

      if (typeof showToast === 'function') {
        showToast('🚀 Умная синхронизация с Yandex S3 запущена в фоне...', 'info');
      }

      pollSmartS3SyncStatus();
    } catch (err) {
      alert('Ошибка сети: ' + err.message);
      if (btn) btn.disabled = false;
    }
  }

  function pollSmartS3SyncStatus() {
    if (smartSyncPollTimer) clearTimeout(smartSyncPollTimer);

    smartSyncPollTimer = setTimeout(async () => {
      try {
        const res = await fetch('/api/sync/smart_s3/status');
        const data = await res.json();
        const st = data.status || {};
        const btn = document.getElementById('btnSmartS3Sync');

        if (st.running) {
          if (btn) {
            btn.innerHTML = `<span>⏳</span> <span>${escapeHtml(st.message || 'Синхронизация...')}</span>`;
          }
          pollSmartS3SyncStatus();
        } else {
          if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<span>☁️</span> <span>Синхронизация S3 и Ozon</span>`;
          }
          if (st.done) {
            if (typeof showToast === 'function') {
              showToast(`✅ Синхронизация завершена! Выгружено фото в S3: <b>${st.uploaded_photos || 0}</b>. База сохранена в облаке.`, 'success');
            } else {
              alert('✅ Синхронизация завершена!');
            }
            if (typeof updateBooksCount === 'function') updateBooksCount();
          } else if (st.error) {
            alert('Ошибка синхронизации: ' + st.error);
          }
        }
      } catch (e) {
        console.error('Ошибка опроса статуса синхронизации:', e);
      }
    }, 2000);
  }

  function loadBookByCurrentArticle() {
    const artNum = document.getElementById('article_number')?.value.trim();
    if (!artNum) {
      alert('Введите номер артикула (например 02882 или 00001)');
      return;
    }
    const cleanNum = artNum.replace(/[^\d]/g, '').padStart(5, '0');
    const fullArt = `DP-B-${cleanNum}`;
    reopenBook(fullArt);
  }

  // Экспорт на window
  window.currentPreviewMode = currentPreviewMode;
  window.getTodayStr = getTodayStr;
  window.updateBooksCount = updateBooksCount;
  window.openReadyFolder = openReadyFolder;
  window.revealTableFile = revealTableFile;
  window.switchPreviewTable = switchPreviewTable;
  window.downloadCurrentPreviewExcel = downloadCurrentPreviewExcel;
  window.downloadPhotosZip = downloadPhotosZip;
  window.openClearTableModal = openClearTableModal;
  window.closeClearTableModal = closeClearTableModal;
  window.onClearConfirmCheckChange = onClearConfirmCheckChange;
  window.executeClearTable = executeClearTable;
  window.refreshPreviewTable = refreshPreviewTable;
  window.deleteBookRow = deleteBookRow;
  window.reopenBook = reopenBook;
  window.updateOzonPhotos = updateOzonPhotos;
  window.updateActiveBookOzonPictures = updateActiveBookOzonPictures;
  window.smartSaveActiveBook = smartSaveActiveBook;
  window.openCatalogSearchModal = openCatalogSearchModal;
  window.closeCatalogSearchModal = closeCatalogSearchModal;
  window.onCatalogSearchInput = onCatalogSearchInput;
  window.searchCatalogBooks = searchCatalogBooks;
  window.loadBookByCurrentArticle = loadBookByCurrentArticle;
  window.startSmartS3Sync = startSmartS3Sync;

})(window);

