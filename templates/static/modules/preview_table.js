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
      const data = window.ApiClient
        ? await window.ApiClient.deleteBookRow(article, currentPreviewMode)
        : await fetch('/api/delete_book_row', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ article, mode: currentPreviewMode })
          }).then(r => r.json());

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

})(window);

