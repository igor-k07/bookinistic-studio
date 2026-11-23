/**
 * system_modals.js: Модальные окна справок, памяток, ключей Gemini и интеграции с Ozon Seller API.
 */

(function (window) {
  'use strict';

  // ---------------------------------------------------------------------------
  // ЕДИНОЕ ОКНО НАСТРОЕК (SETTINGS HUB)
  // ---------------------------------------------------------------------------
  let activeSettingsTab = 'gemini';

  function openSettingsModal(tab = 'gemini') {
    const modal = document.getElementById('settingsModal');
    if (!modal) {
      // Fallback к старым модалкам, если единой модалки нет в DOM
      if (tab === 'gemini') openKeyModal();
      else if (tab === 'ozon') openOzonModal();
      else if (tab === 'storage') openStorageModal();
      else if (tab === 'memos') openMemosModal();
      return;
    }
    modal.classList.remove('hidden');
    switchSettingsTab(tab);
  }

  function closeSettingsModal() {
    const modal = document.getElementById('settingsModal');
    if (modal) modal.classList.add('hidden');
  }

  function switchSettingsTab(tabName) {
    activeSettingsTab = tabName;
    const tabBtns = document.querySelectorAll('.settings-tab-btn');
    tabBtns.forEach(btn => {
      const isTarget = btn.getAttribute('data-tab') === tabName;
      if (isTarget) {
        btn.className = 'settings-tab-btn px-3.5 py-1.5 rounded-xl bg-amber-500 text-slate-950 font-bold text-xs shadow transition';
      } else {
        btn.className = 'settings-tab-btn px-3.5 py-1.5 rounded-xl bg-slate-950/80 hover:bg-slate-800 text-slate-400 hover:text-white font-medium text-xs transition border border-slate-800';
      }
    });

    const panes = document.querySelectorAll('.settings-tab-pane');
    panes.forEach(pane => {
      if (pane.id === 'pane_' + tabName) {
        pane.classList.remove('hidden');
      } else {
        pane.classList.add('hidden');
      }
    });

    if (tabName === 'gemini') {
      loadSavedKey();
    } else if (tabName === 'ozon') {
      loadOzonStatus();
      checkOzonImportStatus();
    } else if (tabName === 'storage') {
      if (typeof loadStorageStats === 'function') loadStorageStats();
    } else if (tabName === 'memos') {
      loadMemosList();
    }
  }

  // ---------------------------------------------------------------------------
  // ПАМЯТКИ И СПРАВОЧНИКИ
  // ---------------------------------------------------------------------------
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
    openSettingsModal('memos');
  }

  function closeMemosModal() {
    closeSettingsModal();
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

  function openCardModal() {
    const modal = document.getElementById('cardModal');
    if (modal) modal.classList.remove('hidden');
  }

  function closeCardModal() {
    const modal = document.getElementById('cardModal');
    if (modal) modal.classList.add('hidden');
  }

  // ---------------------------------------------------------------------------
  // КЛЮЧ GEMINI API
  // ---------------------------------------------------------------------------
  async function loadSavedKey() {
    if (!window.currentApiKey && typeof localStorage !== 'undefined') {
      window.currentApiKey = localStorage.getItem('gemini_api_key') || '';
    }
    updateKeyUi();

    try {
      const res = await fetch('/api/get_key');
      const data = await res.json();
      if (data.key && data.key.trim()) {
        window.currentApiKey = data.key.trim();
        if (typeof localStorage !== 'undefined') {
          localStorage.setItem('gemini_api_key', window.currentApiKey);
        }
      } else if (window.currentApiKey) {
        fetch('/api/save_key', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ key: window.currentApiKey })
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
    if (window.currentApiKey) {
      dot.className = 'w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)]';
      label.textContent = 'Ключ Gemini подключен';
      label.title = 'Ключ активен: ' + window.currentApiKey.substring(0, 6) + '...' + window.currentApiKey.slice(-4);
    } else {
      dot.className = 'w-2 h-2 rounded-full bg-amber-400 animate-pulse';
      label.textContent = 'Ввести API ключ';
      label.title = 'API ключ не настроен';
    }
  }

  function openKeyModal() {
    openSettingsModal('gemini');
  }

  function closeKeyModal() {
    closeSettingsModal();
    const modal = document.getElementById('keyModal');
    if (modal) modal.classList.add('hidden');
  }

  async function saveKeyFromModal() {
    const val = document.getElementById('apiKeyInput')?.value.trim() || '';
    window.currentApiKey = val;
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
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ key: val })
    });
    closeKeyModal();
  }

  // ---------------------------------------------------------------------------
  // ИНТЕГРАЦИЯ С OZON SELLER API
  // ---------------------------------------------------------------------------
  let ozonImportInterval = null;

  async function loadOzonStatus() {
    try {
      const data = window.ApiClient
        ? await window.ApiClient.getOzonStatus()
        : await fetch('/api/ozon/status').then(r => r.json());
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

    const activeProfBadge = document.getElementById('ozonActiveProfileBadge');
    const btnTest = document.getElementById('btnStoreTest');
    const btnPrimary = document.getElementById('btnStorePrimary');

    const activeProf = data?.active_profile || (data?.raw_client_id === '2727930' ? 'test' : 'primary');
    if (activeProfBadge) {
      if (activeProf === 'test') {
        activeProfBadge.className = 'px-2.5 py-0.5 rounded text-[11px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30';
        activeProfBadge.textContent = '🧪 Тестовый (2727930)';
      } else {
        activeProfBadge.className = 'px-2.5 py-0.5 rounded text-[11px] font-mono font-bold bg-sky-500/20 text-sky-300 border border-sky-500/30';
        activeProfBadge.textContent = '🏢 Основной (870997)';
      }
    }

    if (btnTest && btnPrimary) {
      if (activeProf === 'test') {
        btnTest.className = 'py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 transition bg-amber-600/30 border-amber-500 text-amber-200 shadow-sm';
        btnPrimary.className = 'py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 transition bg-slate-800 border-slate-750 text-slate-400 hover:text-white hover:bg-slate-700';
      } else {
        btnTest.className = 'py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 transition bg-slate-800 border-slate-750 text-slate-400 hover:text-white hover:bg-slate-700';
        btnPrimary.className = 'py-2 px-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 transition bg-sky-600/30 border-sky-500 text-sky-200 shadow-sm';
      }
    }
  }

  function openOzonModal() {
    openSettingsModal('ozon');
  }

  function closeOzonModal() {
    closeSettingsModal();
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
      const data = window.ApiClient
        ? await window.ApiClient.saveOzonKeys(clientId, apiKey)
        : await fetch('/api/ozon/save_keys', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ client_id: clientId, api_key: apiKey })
          }).then(r => r.json());

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

  async function switchOzonStore(profileKey) {
    try {
      const data = window.ApiClient
        ? await window.ApiClient.switchOzonProfile(profileKey)
        : await fetch('/api/ozon/switch_profile', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile: profileKey })
          }).then(r => r.json());

      if (data && data.success) {
        const storeTitle = profileKey === 'test' ? 'Тестовый (2727930)' : 'Основной (870997)';
        if (window.showToast) {
          window.showToast(`Магазин Ozon переключен на: ${storeTitle}`, 'success');
        } else {
          alert(`✅ Активный магазин переключен на: ${storeTitle}`);
        }
        await loadOzonStatus();
      } else {
        const errMsg = data?.error || 'Неизвестная ошибка';
        if (window.showToast) {
          window.showToast(`Ошибка переключения: ${errMsg}`, 'error');
        } else {
          alert(`❌ Ошибка переключения: ${errMsg}`);
        }
      }
    } catch (e) {
      console.error('Ошибка switchOzonStore:', e);
      alert('❌ Сбой переключения магазина Ozon: ' + e.message);
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
      const data = window.ApiClient
        ? await window.ApiClient.startOzonImport()
        : await fetch('/api/ozon/import_catalog', { method: 'POST' }).then(r => r.json());

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
        const data = window.ApiClient
          ? await window.ApiClient.getOzonImportStatus()
          : await fetch('/api/ozon/import_status').then(r => r.json());

        if (data.success && data.status) {
          renderOzonImportProgress(data.status);
          if (!data.status.running) {
            clearInterval(ozonImportInterval);
            ozonImportInterval = null;
            loadOzonStatus();
            if (typeof updateBooksCount === 'function') updateBooksCount();
          }
        }
      } catch (e) {
        console.error('Ошибка опроса прогресса импорта:', e);
      }
    }, 1200);
  }

  // Экспорт на window
  window.openSettingsModal = openSettingsModal;
  window.closeSettingsModal = closeSettingsModal;
  window.switchSettingsTab = switchSettingsTab;
  window.openFieldsGuide = openFieldsGuide;
  window.openDocsFolder = openDocsFolder;
  window.openMemosModal = openMemosModal;
  window.closeMemosModal = closeMemosModal;
  window.loadMemosList = loadMemosList;
  window.openCardModal = openCardModal;
  window.closeCardModal = closeCardModal;

  window.loadSavedKey = loadSavedKey;
  window.updateKeyUi = updateKeyUi;
  window.openKeyModal = openKeyModal;
  window.closeKeyModal = closeKeyModal;
  window.saveKeyFromModal = saveKeyFromModal;

  window.loadOzonStatus = loadOzonStatus;
  window.updateOzonUI = updateOzonUI;
  window.openOzonModal = openOzonModal;
  window.closeOzonModal = closeOzonModal;
  window.refreshOzonStatus = refreshOzonStatus;
  window.saveOzonKeysFromModal = saveOzonKeysFromModal;
  window.switchOzonStore = switchOzonStore;
  window.checkOzonImportStatus = checkOzonImportStatus;
  window.renderOzonImportProgress = renderOzonImportProgress;
  window.startOzonCatalogImport = startOzonCatalogImport;
  window.pollOzonImportProgress = pollOzonImportProgress;

})(window);

