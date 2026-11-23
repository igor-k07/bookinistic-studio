/**
 * pipeline.js: Управление пулом фотографий, слотами, драг-н-дропом, ИИ-вырезанием фона и разбором пачки.
 */

    // -------------------------------------------------------------
    // РАБОТА С ПУЛОМ ФОТОГРАФИЙ
    // -------------------------------------------------------------
    async function loadTestBatch() {
      const btn = event.currentTarget;
      const oldHtml = btn.innerHTML;
      btn.innerHTML = '<span>⏳ Загрузка 20 фото...</span>';
      try {
        const res = await fetch('/api/load_test_batch');
        const data = await res.json();
        if (data.photos && data.photos.length > 0) {
          const addedPhotos = [];
          data.photos.forEach(p => {
            const prev = 'data:' + p.mime + ';base64,' + p.data;
            const photoObj = {
              id: 'photo_' + Math.random().toString(36).substr(2, 9),
              name: p.name,
              mime: p.mime,
              data: p.data,
              preview: prev,
              cameraOriginal: prev,
              rawOriginal: prev,
              croppedBase: null,
              isCropped: false,
              isAiProcessed: false,
              assignedBookId: null,
              assignedSlot: null
            };
            photoPool.push(photoObj);
            addedPhotos.push(photoObj);
          });
          renderPool();
          scheduleAutoSave();
          // П. 3.2 спецификации: не вырезаем фон для нераспределенных фото пачки
        }
      } catch (e) {
        alert('Ошибка загрузки теста: ' + e.message);
      } finally {
        btn.innerHTML = oldHtml;
      }
    }

    function resizeImage(file, maxDimension = 1600, quality = 0.85) {
      return new Promise((resolve) => {
        const reader = new FileReader();
        reader.onload = (e) => {
          const img = new Image();
          img.onload = () => {
            let width = img.width;
            let height = img.height;
            if (width > maxDimension || height > maxDimension) {
              if (width > height) {
                height = Math.round((height * maxDimension) / width);
                width = maxDimension;
              } else {
                width = Math.round((width * maxDimension) / height);
                height = maxDimension;
              }
            }
            const canvas = document.createElement('canvas');
            canvas.width = width;
            canvas.height = height;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0, width, height);
            const dataUrl = canvas.toDataURL('image/jpeg', quality);
            resolve({
              name: file.name || 'photo.jpg',
              mime: 'image/jpeg',
              data: dataUrl.split(',')[1],
              preview: dataUrl
            });
          };
          img.src = e.target.result;
        };
        reader.readAsDataURL(file);
      });
    }

    async function handlePoolFiles(e) {
      const files = Array.from(e.target.files).filter(f => f.type.startsWith('image/'));
      if (files.length === 0) return;

      // Быстрая бинарная загрузка через FormData в Photo Engine V2
      try {
        const formData = new FormData();
        formData.append('source', 'desktop');
        files.forEach((f, idx) => {
          formData.append(`file_${idx}`, f, f.name || `photo_${idx}.jpg`);
        });

        showToast(`⏳ Загрузка ${files.length} фото в хранилище ассетов...`);
        const resp = await fetch('/api/assets/upload', {
          method: 'POST',
          body: formData
        });
        const data = await resp.json();
        if (data.success && data.assets && data.assets.length > 0) {
          data.assets.forEach(ast => {
            photoPool.push({
              id: ast.id,
              name: ast.name || ast.filename || 'photo.jpg',
              preview: ast.preview_url,
              cameraOriginal: ast.full_url,
              rawOriginal: ast.full_url,
              croppedBase: null,
              isCropped: false,
              isAiProcessed: false,
              assignedBookId: null,
              assignedSlot: null,
              status: ast.status
            });
          });
          renderPool();
          scheduleAutoSave();
          showToast(`✅ ${data.assets.length} фото загружено в память сервера!`);
          e.target.value = '';
          return;
        }
      } catch (err) {
        console.warn('Откат на клиентский ресайз при ошибке бинарной загрузки:', err);
      }

      // Резервный клиентский путь (fallback)
      const addedPhotos = [];
      for (const f of files) {
        const res = await resizeImage(f);
        const photoObj = {
          id: 'photo_' + Math.random().toString(36).substr(2, 9),
          name: res.name,
          mime: res.mime,
          data: res.data,
          preview: res.preview,
          cameraOriginal: res.preview,
          rawOriginal: res.preview,
          croppedBase: null,
          isCropped: false,
          isAiProcessed: false,
          assignedBookId: null,
          assignedSlot: null
        };
        photoPool.push(photoObj);
        addedPhotos.push(photoObj);
      }
      renderPool();
      scheduleAutoSave();
      e.target.value = '';
    }

    function deletePhotoFromPool(photoId, e) {
      if (e) {
        e.stopPropagation();
        e.preventDefault();
      }
      if (!photoId) return;

      const idx = photoPool.findIndex(p => p.id === photoId);
      if (idx === -1) return;

      const photo = photoPool[idx];
      const photoName = photo.name || `#${idx + 1}`;

      // Удаляем фото из массива пула
      photoPool.splice(idx, 1);

      // Отменяем отложенную S3 выгрузку если была запланирована
      if (proactiveS3Timers.has(photoId)) {
        clearTimeout(proactiveS3Timers.get(photoId));
        proactiveS3Timers.delete(photoId);
      }

      // Безусловно очищаем фото из слотов любых книг и перерисовываем слоты
      removePhotoFromSlots(photoId);
      renderActiveBookSlots();

      // Очищаем файл и запись ассета на диске и в SQLite
      if (photoId && (photoId.startsWith('ast_') || photoId.startsWith('photo_'))) {
        try {
          fetch('/api/assets/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ asset_id: photoId })
          }).catch(() => {});
        } catch(e) {}
      }

      // Если удалено выбранное фото, выбираем следующее свободное
      if (selectedPoolPhotoId === photoId) {
        const remainingUnassigned = photoPool.filter(p => !p.assignedBookId);
        selectedPoolPhotoId = remainingUnassigned.length > 0 ? remainingUnassigned[0].id : null;
      }

      renderPool();
      renderBooksTabs();
      scheduleAutoSave();

      if (typeof showToast === 'function') {
        showToast(`🗑️ Фото «${photoName}» удалено из пула`);
      }
    }

    function deleteSelectedPhotoFromPool() {
      if (selectedPoolPhotoId) {
        deletePhotoFromPool(selectedPoolPhotoId);
      } else {
        if (typeof showToast === 'function') {
          showToast('ℹ️ Сначала выберите фото в пуле для удаления');
        }
      }
    }

    function clearPool() {
      // Собираем все ID фотографий, которые уже распределены по слотам любых книг сессии
      const assignedIds = new Set();
      (window.booksSession || []).forEach(b => {
        if (!b.slots) return;
        ['cover_front', 'cover_back', 'info_pages', 'illustrations', 'mantra_defects'].forEach(s => {
          const val = b.slots[s];
          if (!val) return;
          if (Array.isArray(val)) {
            val.forEach(p => { if (p && p.id) assignedIds.add(p.id); });
          } else if (val && val.id) {
            assignedIds.add(val.id);
          }
        });
      });

      // Свободные фото в пуле (не привязанные ни к одному слоту)
      const freePhotos = photoPool.filter(p => !assignedIds.has(p.id) && !p.assignedBookId);

      if (freePhotos.length === 0) {
        if (typeof showToast === 'function') {
          showToast('ℹ️ В свободном пуле нет фотографий для очистки (все фото уже распределены по слотам книг).');
        } else {
          alert('В свободном пуле нет фотографий для очистки (все фото уже распределены по слотам книг).');
        }
        return;
      }

      const confirmed = confirm(
        `🧹 Очистить свободный пул?\n\n` +
        `Будет удалено нераспределенных фото: ${freePhotos.length} шт.\n\n` +
        `Все фотографии в слотах книг (${assignedIds.size} шт.) останутся в полной сохранности!`
      );
      if (!confirmed) return;

      // Оставляем в photoPool ТОЛЬКО те фотографии, которые распределены по слотам!
      photoPool = photoPool.filter(p => assignedIds.has(p.id) || Boolean(p.assignedBookId));
      selectedPoolPhotoId = null;

      // Удаляем временные ассеты нераспределенных фото с диска и из базы
      freePhotos.forEach(p => {
        if (p && p.id && (p.id.startsWith('ast_') || p.id.startsWith('photo_'))) {
          try {
            fetch('/api/assets/delete', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ asset_id: p.id })
            }).catch(() => {});
          } catch(e) {}
        }
      });

      renderPool();
      renderActiveBookSlots();
      scheduleAutoSave();

      if (typeof showToast === 'function') {
        showToast(`🧹 Свободный пул очищен! Удалено ${freePhotos.length} фото. Фотографии в слотах сохранены.`);
      }
    }

    // poolCardScale объявлен в state.js
    try {
      const savedScale = localStorage.getItem('bookinistic_pool_scale');
      if (savedScale && ['normal', 'large', 'xlarge'].includes(savedScale)) poolCardScale = savedScale;
    } catch(e) {}

    function setPoolScale(scale) {
      poolCardScale = scale;
      try { localStorage.setItem('bookinistic_pool_scale', scale); } catch(e) {}
      ['normal', 'large', 'xlarge'].forEach(s => {
        const btn = document.getElementById('scaleBtn_' + s);
        if (!btn) return;
        if (s === scale) {
          btn.className = 'px-2.5 py-1 text-xs rounded-lg transition font-bold bg-amber-500 text-slate-950 shadow-sm';
        } else {
          btn.className = 'px-2.5 py-1 text-xs rounded-lg transition font-medium text-slate-400 hover:text-white';
        }
      });
      renderPool();
    }

    async function batchWhitenAllPool() {
      const unedited = photoPool.filter(p => !isPhotoProcessed(p));
      if (unedited.length === 0) {
        alert('Все фотографии в пуле уже обработаны!');
        return;
      }
      const btn = document.getElementById('batchWhitenBtn');
      const oldHtml = btn ? btn.innerHTML : '';
      if (btn) btn.disabled = true;
      let count = 0;
      for (const p of unedited) {
        p.whiten = 85;
        p.brightness = 4;
        p.contrast = 8;
        p.isProcessed = true;
        await processPhotoOffscreen(p);
        count++;
        if (btn) btn.innerHTML = `<span>⏳ Отбеливание... (${count}/${unedited.length})</span>`;
      }
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = oldHtml;
      }
      renderPool();
      renderActiveBookSlots();
      scheduleAutoSave();
    }

    function updateSelectedToolbar() {
      const toolbar = document.getElementById('poolSelectedToolbar');
      if (!toolbar) return;

      const unassignedPhotos = photoPool.filter(p => !p.assignedBookId);
      if (photoPool.length === 0 || unassignedPhotos.length === 0) {
        toolbar.classList.add('hidden');
        selectedPoolPhotoId = null;
        return;
      }
      toolbar.classList.remove('hidden');

      let photo = unassignedPhotos.find(p => p.id === selectedPoolPhotoId);
      if (!photo) {
        photo = unassignedPhotos[0];
        if (photo) selectedPoolPhotoId = photo.id;
      }

      const nameEl = document.getElementById('poolSelectedName');
      const badgeEl = document.getElementById('poolSelectedBadge');
      const statusBadge = document.getElementById('poolSelectedStatusBadge');
      const bookLabel = document.getElementById('poolSelectedActiveBookLabel');

      const curBook = getActiveBook();
      if (bookLabel && curBook) {
        const art = (curBook.formData && curBook.formData.article) || curBook.article || `Книга #${curBook.id}`;
        bookLabel.textContent = `${art} (#${curBook.id})`;
      }

      if (photo) {
        const unassignedIdx = unassignedPhotos.indexOf(photo);
        const totalIdx = photoPool.indexOf(photo);
        if (nameEl) nameEl.textContent = photo.name;
        if (badgeEl) {
          badgeEl.classList.remove('hidden');
          badgeEl.textContent = `#${totalIdx + 1} (${unassignedIdx + 1} из ${unassignedPhotos.length})`;
        }
        if (statusBadge) {
          statusBadge.classList.remove('hidden');
          if (isPhotoProcessed(photo)) {
            statusBadge.innerHTML = `<span class="px-2 py-0.5 rounded-md bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 text-[10px] font-bold inline-flex items-center gap-1 shadow-sm"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span>✨ Обработано</span>`;
          } else {
            statusBadge.innerHTML = `<span class="px-2 py-0.5 rounded-md bg-slate-800 text-amber-300 border border-amber-500/40 text-[10px] font-semibold inline-flex items-center gap-1 shadow-sm"><span class="w-1.5 h-1.5 rounded-full bg-amber-400"></span>📷 Исходник</span>`;
          }
        }
        const revertBtn = document.getElementById('btnRevertSelected');
        if (revertBtn) {
          if (isPhotoProcessed(photo)) {
            revertBtn.classList.remove('hidden');
          } else {
            revertBtn.classList.add('hidden');
          }
        }
      } else {
        if (nameEl) nameEl.textContent = 'Нет выбранного фото';
        if (badgeEl) badgeEl.classList.add('hidden');
        if (statusBadge) statusBadge.classList.add('hidden');
        const revertBtn = document.getElementById('btnRevertSelected');
        if (revertBtn) revertBtn.classList.add('hidden');
      }
    }

    function openStudioForSelected() {
      if (selectedPoolPhotoId) openPhotoStudio(selectedPoolPhotoId);
    }

    function cropSelectedPhoto() {
      if (selectedPoolPhotoId) openPhotoStudio(selectedPoolPhotoId, null, 'crop');
    }

    function rotateSelectedPhoto(deg) {
      if (selectedPoolPhotoId) quickRotatePhoto(selectedPoolPhotoId, deg);
    }

    function whitenSelectedPhoto() {
      if (selectedPoolPhotoId) quickAiProcessPhoto(selectedPoolPhotoId);
    }

    function recognizeSelectedPhoto() {
      if (!selectedPoolPhotoId) {
        const photo = photoPool.find(p => !p.assignedBookId);
        if (photo) {
          selectedPoolPhotoId = photo.id;
          updateSelectedToolbar();
        } else {
          alert('Сначала загрузите или выберите фото в пуле!');
          return;
        }
      }
      recognizeSinglePhoto(selectedPoolPhotoId);
    }

    function recognizeSinglePhoto(photoId, e) {
      if (e) e.stopPropagation();
      const photo = findPhotoById(photoId);
      if (!photo) return;
      selectedPoolPhotoId = photo.id;
      updateSelectedToolbar();
      if (!photo.assignedSlot) {
        assignPhotoToSlot(photo.id, 'cover_front');
      }
      runAiForActiveBook();
    }

    function assignSelectedToSlot(slotName) {
      if (selectedPoolPhotoId) assignPhotoToSlot(selectedPoolPhotoId, slotName);
    }

    function isPhotoInAnyBookSlot(photoId) {
      if (!photoId) return false;
      return (window.booksSession || []).some(b => {
        if (!b || !b.slots) return false;
        return [
          b.slots.cover_front,
          ...(Array.isArray(b.slots.cover_back) ? b.slots.cover_back : (b.slots.cover_back ? [b.slots.cover_back] : [])),
          ...(b.slots.info_pages || []),
          ...(b.slots.illustrations || []),
          ...(b.slots.mantra_defects || [])
        ].some(s => s && s.id === photoId);
      });
    }
    function getPhotoDisplayUrl(p) {
      if (!p) return '';
      // 1. Свежий in-memory срез из canvas редактора (data: или blob:)
      if (p.preview && typeof p.preview === 'string' && (p.preview.startsWith('data:') || p.preview.startsWith('blob:'))) {
        return p.preview;
      }
      if (p.croppedBase && typeof p.croppedBase === 'string' && (p.croppedBase.startsWith('data:') || p.croppedBase.startsWith('blob:'))) {
        return p.croppedBase;
      }
      // 2. Чистые base64 данные (если есть)
      if (p.data && typeof p.data === 'string' && !p.data.startsWith('/session_photos/')) {
        return p.data.startsWith('data:') ? p.data : `data:image/jpeg;base64,${p.data}`;
      }
      // 3. Постоянная надежная локальная ссылка из хранилища books_vault на диске Mac (0 мс задержки)
      if (p.url && typeof p.url === 'string' && p.url.startsWith('/vault/')) {
        return p.url;
      }
      if (p.preview && typeof p.preview === 'string' && p.preview.startsWith('/vault/')) {
        return p.preview;
      }
      // 4. Локальные сессионные фото и ассеты
      if (p.preview && typeof p.preview === 'string' && (p.preview.startsWith('/session_photos/') || p.preview.startsWith('/api/assets/') || p.preview.startsWith('/inbox/'))) {
        return p.preview;
      }
      // 5. Актуальная ссылка на постоянное облако Yandex S3 CDN (если локального файла нет)
      if (p.s3_url && typeof p.s3_url === 'string') {
        return p.s3_url;
      }
      // 6. Превью любого другого формата
      if (p.preview && typeof p.preview === 'string') {
        return p.preview;
      }
      // 7. Отредактированный срез из сессии
      if (p.croppedBase && typeof p.croppedBase === 'string') {
        return p.croppedBase;
      }
      // 8. Постоянная ссылка из vault / asset
      if (p.url && typeof p.url === 'string') {
        return p.url;
      }
      // 9. Исходный снимок с камеры
      return p.cameraOriginal || p.rawOriginal || '';
    }
    window.getPhotoDisplayUrl = getPhotoDisplayUrl;
    window.isPhotoInAnyBookSlot = isPhotoInAnyBookSlot;

    let currentLightboxPhotoId = null;

    function inspectPhotoLightbox(photoId, e) {
      if (e) {
        e.stopPropagation();
        e.preventDefault();
      }
      const photo = findPhotoById(photoId);
      if (!photo) return;

      currentLightboxPhotoId = photo.id;
      const modal = document.getElementById('photoLightboxModal');
      const img = document.getElementById('lightboxImg');
      const titleEl = document.getElementById('lightboxTitle');
      const resEl = document.getElementById('lightboxRes');
      const slotEl = document.getElementById('lightboxSlot');
      const badgeEl = document.getElementById('lightboxBadge');

      if (!modal || !img) return;

      const src = getPhotoDisplayUrl(photo);
      img.src = src;

      if (titleEl) {
        titleEl.textContent = photo.name || photo.filename || photo.id;
      }

      if (resEl) {
        resEl.textContent = 'Определение разрешения...';
        const temp = new Image();
        temp.onload = () => {
          if (resEl && currentLightboxPhotoId === photo.id) {
            resEl.textContent = `${temp.naturalWidth} × ${temp.naturalHeight} px`;
          }
        };
        temp.src = src;
      }

      if (slotEl) {
        const slotNames = {
          'cover_front': '1. Главная обложка (Лицо)',
          'cover_back': '2. Задняя сторона (Оборот)',
          'info_pages': '3. Титул / Год / Страницы (ИИ)',
          'illustrations': '4. Иллюстрации и развороты',
          'mantra_defects': '5. Дефекты и нюансы'
        };
        slotEl.textContent = slotNames[photo.assignedSlot] || (photo.assignedSlot ? `Слот: ${photo.assignedSlot}` : 'В пуле (без слота)');
      }

      if (badgeEl) {
        const processed = isPhotoProcessed(photo);
        if (processed) {
          badgeEl.className = 'px-2.5 py-1 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold text-xs shadow flex items-center gap-1.5';
          badgeEl.innerHTML = `<span>✅</span> <span>ГОТОВО К OZON (ФИНАЛЬНЫЙ СРЕЗ)</span>`;
        } else {
          badgeEl.className = 'px-2.5 py-1 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30 font-bold text-xs shadow flex items-center gap-1.5';
          badgeEl.innerHTML = `<span>📷</span> <span>СЫРОЙ ИСХОДНИК С КАМЕРЫ</span>`;
        }
      }

      modal.classList.remove('hidden');
      modal.classList.add('flex');
    }

    function closePhotoLightbox() {
      const modal = document.getElementById('photoLightboxModal');
      if (modal) {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
      }
      currentLightboxPhotoId = null;
    }

    function openStudioFromLightbox() {
      const pid = currentLightboxPhotoId;
      closePhotoLightbox();
      if (pid) {
        openPhotoStudio(pid);
      }
    }

    window.inspectPhotoLightbox = inspectPhotoLightbox;
    window.closePhotoLightbox = closePhotoLightbox;
    window.openStudioFromLightbox = openStudioFromLightbox;

    // Esc handler for lightbox modal
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        const modal = document.getElementById('photoLightboxModal');
        if (modal && !modal.classList.contains('hidden')) {
          closePhotoLightbox();
        }
      }
    });

    function renderPool() {
      const container = document.getElementById('poolContainer');
      const counter = document.getElementById('poolCounterBadge');
      const unassignedPhotos = photoPool.filter(p => !p.assignedBookId && !isPhotoInAnyBookSlot(p.id));
      const unassignedCount = unassignedPhotos.length;
      const processedCount = photoPool.filter(p => isPhotoProcessed(p)).length;
      const rawCount = photoPool.length - processedCount;

      if (counter) {
        counter.innerHTML = `📊 <span class="font-bold text-amber-300">${unassignedCount} свободных</span> / ${photoPool.length} всего &bull; <span class="text-emerald-400 font-bold">✨ ${processedCount} обраб.</span> &bull; <span class="text-slate-400 font-medium">📷 ${rawCount} исх.</span>`;
      }

      if (photoPool.length === 0) {
        container.innerHTML = '<div class="text-center py-12 w-full text-xs text-slate-500 border border-dashed border-slate-800 rounded-2xl bg-slate-950/40 flex flex-col items-center justify-center gap-2"><span class="text-2xl">📸</span><span>Пул пуст. Снимите пачку книг на телефон через QR-код или нажмите «📁 С диска»</span></div>';
        updateSelectedToolbar();
        return;
      }

      if (unassignedPhotos.length === 0) {
        container.innerHTML = `
          <div class="text-center py-12 px-6 w-full text-xs border border-dashed border-emerald-700/60 rounded-2xl bg-emerald-950/20 flex flex-col items-center justify-center gap-2 pointer-events-none select-none">
            <span class="text-3xl">🎉</span>
            <span class="font-bold text-emerald-300 text-sm">Все фото (${photoPool.length} шт.) распределены по книгам!</span>
            <span class="text-slate-400">Перетащите сюда фото из слотов книги или нажмите «✕» на миниатюре слота, чтобы вернуть кадр в общий пул.</span>
          </div>
        `;
        updateSelectedToolbar();
        return;
      }

      // Настройки масштаба карточки
      const scaleConfig = {
        normal: { cardW: 'w-48', minH: 'min-h-[290px]', imgH: 'h-44' },
        large:  { cardW: 'w-60', minH: 'min-h-[350px]', imgH: 'h-56' },
        xlarge: { cardW: 'w-72', minH: 'min-h-[420px]', imgH: 'h-68' }
      };
      const curScale = scaleConfig[poolCardScale] || scaleConfig.large;

      container.innerHTML = unassignedPhotos.map((p) => {
        const globalIdx = photoPool.indexOf(p);
        const isSelected = p.id === selectedPoolPhotoId;
        const processed = isPhotoProcessed(p);
        const isBusy = Boolean(p.isAiProcessing || p.isProcessing);

        return `
          <div class="relative shrink-0 group rounded-2xl overflow-hidden border ${isSelected ? 'border-amber-400 ring-2 ring-amber-400/50 shadow-xl shadow-amber-400/20' : 'border-slate-800 hover:border-slate-600'} ${curScale.cardW} ${curScale.minH} bg-slate-950 flex flex-col justify-between p-1.5 transition-all cursor-grab active:cursor-grabbing select-none shadow-md ${isBusy ? 'opacity-90 select-none' : ''}"
               draggable="${!isBusy}" ondragstart="handlePhotoDragStart(event, '${p.id}', 'pool')" ondragend="handlePhotoDragEnd(event)" onclick="selectPoolPhoto('${p.id}')">

            
            <!-- ВЕРХНЯЯ ПАНЕЛЬКА КАРТОЧКИ: ИНДЕКС, СТАТУС И БЫСТРЫЕ КНОПКИ -->
            <div class="flex items-center justify-between gap-1 mb-1 z-30" ondblclick="event.stopPropagation()">
              <div class="flex items-center gap-1 min-w-0">
                <span class="px-1.5 py-0.5 rounded bg-black/85 text-[10px] font-mono font-bold text-slate-300 shadow">#${globalIdx+1}</span>
                ${isBusy ? `
                  <span class="px-1.5 py-0.5 rounded bg-amber-500 text-slate-950 text-[9px] font-black animate-pulse shadow">⏳ ОБРАБОТКА...</span>
                ` : (processed ? `
                  <span class="px-1.5 py-0.2 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[9px] font-bold shadow flex items-center gap-1" title="Финальная версия готова к публикации на Ozon">
                    <span>✅</span> <span>ГОТОВО К OZON</span>
                  </span>
                ` : `
                  <span class="px-1.5 py-0.2 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30 text-[9px] font-bold shadow flex items-center gap-1" title="Исходный снимок без обрезки и фильтров">
                    <span>📷</span> <span>ИСХОДНИК</span>
                  </span>
                `)}
                ${p.isCropped ? '<span class="px-1.5 py-0.2 rounded bg-slate-850 text-slate-300 border border-slate-750 text-[8px]" title="Кадрировано под пропорции">✂️ КРОП</span>' : ''}
                ${p.s3_url ? '<span class="px-1.5 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800 text-[9px] font-bold shadow" title="Выгружено в Yandex S3 CDN">☁️ S3</span>' : ''}
                ${p.status === 'ERROR' ? `<span class="px-1.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-700 text-[9px] font-bold shadow cursor-pointer" onclick="quickAiProcessPhoto('${p.id}', event)" title="Ошибка обработки. Кликните для повтора">⚠️ СБОЙ</span>` : ''}
              </div>
              <div class="flex items-center gap-0.5 bg-black/90 backdrop-blur-sm p-0.5 rounded-lg shadow border border-slate-700/60 shrink-0">
                <button type="button" onclick="inspectPhotoLightbox('${p.id}', event)" class="p-1 rounded hover:bg-sky-600 hover:text-white text-sky-300 text-xs transition" title="👁️ Быстрый просмотр 1:1 (как в Ozon)">👁️</button>
                <button type="button" onclick="quickAiProcessPhoto('${p.id}', event)" class="p-1 rounded hover:bg-violet-600 hover:text-white text-violet-300 text-xs transition" title="✨ ИИ-вырезание фона на чистый белый Ozon (rembg)">✨</button>
                <button type="button" onclick="openPhotoStudio('${p.id}', event)" class="p-1 rounded hover:bg-amber-500 hover:text-black text-amber-300 text-xs transition" title="✏️ Редактор: кадрирование и фильтры">✏️</button>
                ${(p.cameraOriginal || p.isAiProcessed || processed || p.isCropped || (p.history && p.historyIndex > 0)) ? `<button type="button" onclick="revertPhotoToOriginal('${p.id}', event)" class="p-1 rounded bg-rose-950/60 hover:bg-rose-900 border border-rose-700/50 text-rose-300 hover:text-white text-xs transition flex items-center justify-center shadow-xs" title="↩️ Вернуть исходное фото с камеры (1 шаг)">↩️</button>` : ''}
                <button type="button" onclick="deletePhotoFromPool('${p.id}', event)" class="p-1 rounded hover:bg-rose-600 hover:text-white text-rose-400 hover:text-white text-xs transition flex items-center justify-center shadow-xs" title="🗑️ Удалить фото из пула">🗑️</button>
              </div>

            </div>

            <!-- БОЛЬШАЯ КАРТИНКА ПРЕВЬЮ В РЕЖИМЕ OBJECT-CONTAIN -->
            <div class="relative w-full ${curScale.imgH} rounded-xl overflow-hidden bg-slate-950/80 border border-slate-800/80 group-hover:border-slate-700 transition cursor-pointer flex items-center justify-center p-1.5 shadow-inner"
                 ondblclick="openPhotoStudio('${p.id}', event)" title="Двойной клик по картинке — открыть фоторедактор">
              <img src="${getPhotoDisplayUrl(p)}" class="max-w-full max-h-full object-contain pointer-events-none drop-shadow select-none transition-transform duration-200" loading="lazy" onerror="const alt='${p.url || p.s3_url || p.preview || p.cameraOriginal || ''}'; if(alt && this.src!==alt) this.src=alt;">

              <!-- КНОПКА БЫСТРОГО УДАЛЕНИЯ ИЗ ПУЛА В ЛЕВОМ ВЕРХНЕМ УГЛУ КАРТИНКИ -->
              <button type="button" onclick="deletePhotoFromPool('${p.id}', event)" ondblclick="event.stopPropagation()" class="absolute top-2 left-2 w-8 h-8 rounded-lg bg-black/85 hover:bg-rose-600 hover:text-white text-slate-300 border border-slate-700/80 shadow-md flex items-center justify-center text-xs transition active:scale-90 z-10" title="🗑️ Удалить фото из пула">🗑️</button>

              <!-- ФИКСИРОВАННАЯ КНОПКА РАЗВОРОТА НА 90° В ПРАВОМ ВЕРХНЕМ УГЛУ КАРТИНКИ -->
              <button type="button" onclick="quickRotatePhoto('${p.id}', 90, event)" ondblclick="event.stopPropagation()" class="absolute top-2 right-2 w-8 h-8 rounded-lg bg-black/85 hover:bg-amber-500 hover:text-black text-amber-300 border border-slate-700/80 shadow-md flex items-center justify-center text-xs transition active:scale-90 z-10" title="Повернуть на 90° (всегда на этом месте)">🔄</button>

              <!-- БЛОКИРОВКА И СПИННЕР ПРИ ОБРАБОТКЕ -->
              ${isBusy ? `
                <div class="absolute inset-0 bg-slate-950/70 backdrop-blur-xs flex flex-col items-center justify-center gap-2 z-20 pointer-events-none select-none">
                  <div class="w-8 h-8 border-3 border-amber-400 border-t-transparent rounded-full animate-spin"></div>
                  <span class="text-[10px] font-bold text-amber-300 tracking-wide animate-pulse">${p.isAiProcessing ? 'ИИ вырезает...' : 'Отбеливание...'}</span>
                </div>
              ` : ''}
            </div>

            <!-- НИЖНЯЯ ПАНЕЛЬ: ВЫБОР ИЗ 5 КАТЕГОРИЙ С ПОЛНЫМ ТЕКСТОМ -->
            <div class="mt-1 pt-1 border-t border-slate-850 flex flex-col gap-1" ondblclick="event.stopPropagation()">
              <div class="flex flex-col gap-1 w-full">
                <div class="grid grid-cols-2 gap-1 w-full text-[10px]">
                  <button type="button" onclick="assignPhotoToSlot('${p.id}', 'cover_front', event)" class="px-1.5 py-1 rounded-lg bg-amber-600/90 hover:bg-amber-500 text-white font-bold truncate transition shadow-xs text-center" title="1. Главное фото карточки Ozon (лицо книги)">🌟 1. Обложка</button>
                  <button type="button" onclick="assignPhotoToSlot('${p.id}', 'cover_back', event)" class="px-1.5 py-1 rounded-lg bg-sky-600/90 hover:bg-sky-500 text-white font-bold truncate transition shadow-xs text-center" title="2. Задник книги, штрихкод">🔄 2. Задник</button>
                </div>
                <div class="grid grid-cols-3 gap-1 w-full text-[9px]">
                  <button type="button" onclick="assignPhotoToSlot('${p.id}', 'info_pages', event)" class="px-1 py-1 rounded bg-emerald-600/90 hover:bg-emerald-500 text-white font-bold truncate transition shadow-xs text-center" title="3. Титульный лист и выходные данные (ИИ)">📄 3. Титул</button>
                  <button type="button" onclick="assignPhotoToSlot('${p.id}', 'illustrations', event)" class="px-1 py-1 rounded bg-indigo-600/90 hover:bg-indigo-500 text-white font-bold truncate transition shadow-xs text-center" title="4. Иллюстрации и развороты">🎨 4. Илл.</button>
                  <button type="button" onclick="assignPhotoToSlot('${p.id}', 'mantra_defects', event)" class="px-1 py-1 rounded bg-rose-600/90 hover:bg-rose-500 text-white font-bold truncate transition shadow-xs text-center" title="5. Дефекты и нюансы (ИИ)">⚠️ 5. Дефекты</button>
                </div>
              </div>
              
              <!-- ИМЯ ФАЙЛА В САМОМ НИЗУ -->
              <div class="flex items-center justify-between text-[9px] font-mono text-slate-500 pt-0.5">
                <span class="truncate max-w-[150px]">${p.name}</span>
                <span class="text-slate-400 font-sans">свободно</span>
              </div>
            </div>

          </div>
        `;
      }).join('');

      updateSelectedToolbar();
    }

    function selectPoolPhoto(id) {
      selectedPoolPhotoId = id;
      renderPool();
    }

    // Горячие клавиши 1-5 для быстрого раскидывания выбранного кадра и Delete для удаления
    window.addEventListener('keydown', (e) => {
      if (['input', 'textarea', 'select'].includes(document.activeElement.tagName.toLowerCase())) return;
      if (!selectedPoolPhotoId) return;

      if (e.key === 'Delete' || e.key === 'Backspace') {
        e.preventDefault();
        deleteSelectedPhotoFromPool();
        return;
      }

      const slotMap = {
        '1': 'cover_front',
        '2': 'cover_back',
        '3': 'info_pages',
        '4': 'illustrations',
        '5': 'mantra_defects'
      };

      if (slotMap[e.key]) {
        assignPhotoToSlot(selectedPoolPhotoId, slotMap[e.key]);
      }
    });

    // -------------------------------------------------------------


// -------------------------------------------------------------
// СЛОТЫ И ДРАГ-Н-ДРОП
// -------------------------------------------------------------
    const proactiveS3Timers = new Map();

    function scheduleProactiveS3Upload(photoId, slotName, delayMs = 2500) {
      if (proactiveS3Timers.has(photoId)) {
        clearTimeout(proactiveS3Timers.get(photoId));
        proactiveS3Timers.delete(photoId);
      }

      const timer = setTimeout(async () => {
        proactiveS3Timers.delete(photoId);

        // Если в данный момент открыт фоторедактор для этого фото, выгрузку не делаем
        if (typeof isStudioOpen !== 'undefined' && isStudioOpen && typeof currentEditingPhoto !== 'undefined' && currentEditingPhoto && currentEditingPhoto.id === photoId) {
          return;
        }

        const photo = findPhotoById(photoId);
        if (!photo || !photo.assignedSlot) return;
        if (photo.is_s3_uploaded && photo.s3_url) return;

        const book = getActiveBook();
        const article = (book && book.formData && book.formData.article) || (book && book.article) || document.getElementById('article')?.value?.trim();
        if (!article) return;
        const title = (book && book.formData && book.formData.title) || document.getElementById('title')?.value?.trim();
        // Защита: не создаем в S3 временную безымянную папку, пока реальное название книги неизвестно
        if (!title || title.trim().toLowerCase() === 'book' || title.trim() === 'Без названия') {
          return;
        }

        let photoIndex = 1;
        if (['cover_back', 'info_pages', 'illustrations', 'mantra_defects'].includes(photo.assignedSlot)) {
          const list = Array.isArray(book.slots[photo.assignedSlot]) ? book.slots[photo.assignedSlot] : [];
          const idx = list.findIndex(p => p && p.id === photoId);
          if (idx >= 0) photoIndex = idx + 1;
        }

        const payloadData = photo.data || photo.preview || photo.croppedBase || photo.cameraOriginal;
        if (!payloadData) return;

        try {
          const res = await ApiClient.uploadSlotPhoto(article, title, photo.assignedSlot, photoIndex, payloadData, photoId);
          if (res && res.success && res.s3_url) {
            photo.s3_url = res.s3_url;
            photo.is_s3_uploaded = true;
            if (!photo.preview) photo.preview = res.s3_url;
            if (window.EventBus) window.EventBus.emit('photo:s3-uploaded', { photoId, s3_url: res.s3_url });
            renderActiveBookSlots();
          }
        } catch (err) {
          console.warn(`[Proactive S3] Фоновая выгрузка ${photoId}:`, err);
        }
      }, delayMs);

      proactiveS3Timers.set(photoId, timer);
    }

    function assignPhotoToSlot(photoId, slotName, e) {
      if (e) e.stopPropagation();
      const photo = photoPool.find(p => p.id === photoId);
      if (!photo) return;

      const book = getActiveBook();

      // Очищаем старую привязку фото если было в другом месте
      if (photo.assignedBookId) {
        removePhotoFromSlots(photo.id);
      }

      photo.assignedBookId = book.id;
      photo.assignedSlot = slotName;

      if (['cover_back', 'info_pages', 'illustrations', 'mantra_defects'].includes(slotName)) {
        if (!Array.isArray(book.slots[slotName])) {
          book.slots[slotName] = book.slots[slotName] ? [book.slots[slotName]] : [];
        }
        // Множественный слот: добавляем фото в массив если его там еще нет
        if (!book.slots[slotName].some(p => p.id === photo.id)) {
          book.slots[slotName].push(photo);
        }
      } else {
        // Одиночный слот (только передняя обложка): заменяем и возвращаем старое в пул
        if (book.slots[slotName]) {
          const oldPhotoId = book.slots[slotName].id;
          book.slots[slotName].assignedBookId = null;
          book.slots[slotName].assignedSlot = null;
          if (oldPhotoId) {
            const oldInPool = photoPool.find(p => p.id === oldPhotoId);
            if (oldInPool) {
              oldInPool.assignedBookId = null;
              oldInPool.assignedSlot = null;
            }
          }
        }
        book.slots[slotName] = photo;
      }

      // Если было выбрано это фото, переключаем выбор на следующее свободное в пуле
      if (selectedPoolPhotoId === photoId) {
        const remaining = photoPool.filter(p => !p.assignedBookId && p.id !== photoId);
        selectedPoolPhotoId = remaining.length > 0 ? remaining[0].id : null;
      }

      // Согласно п. 3.2 спецификации: удаление фона нейросетью запускается ТОЛЬКО для обложки и задника!
      if (slotName === 'cover_front' || slotName === 'cover_back') {
        queueAiBackgroundRemoval(photo.id);
      }

      // Шаг 3 спецификации: планируем упреждающую фоновую выгрузку в S3 с таймером покоя 2.5 сек
      scheduleProactiveS3Upload(photo.id, slotName, 2500);

      // Синхронизация привязки слота с SQLite-реестром ассетов
      if (photo.id && (photo.id.startsWith('ast_') || photo.id.startsWith('photo_'))) {
        try {
          fetch('/api/assets/assign', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              asset_id: photo.id,
              slot: slotName,
              book_id: book.id,
              book_article: book.article
            })
          }).catch(e => {});
        } catch(e) {}
      }

      renderPool();
      renderBooksTabs();
      renderActiveBookSlots();
      scheduleAutoSave();
    }

    function unassignPhoto(photoId, e) {
      if (e) e.stopPropagation();
      if (proactiveS3Timers.has(photoId)) {
        clearTimeout(proactiveS3Timers.get(photoId));
        proactiveS3Timers.delete(photoId);
      }
      let photo = photoPool.find(p => p.id === photoId);
      if (photo) {
        photo.assignedBookId = null;
        photo.assignedSlot = null;
        photo.is_s3_uploaded = false;
        photo.s3_url = null;
        selectedPoolPhotoId = photo.id;
      } else {
        // Если фото было в слоте, но отсутствовало в photoPool — возвращаем его в пул
        for (const b of (window.booksSession || [])) {
          if (b.slots) {
            const allSlotPhotos = [
              b.slots.cover_front,
              ...(Array.isArray(b.slots.cover_back) ? b.slots.cover_back : (b.slots.cover_back ? [b.slots.cover_back] : [])),
              ...(b.slots.info_pages || []),
              ...(b.slots.illustrations || []),
              ...(b.slots.mantra_defects || [])
            ].filter(Boolean);
            const foundInSlot = allSlotPhotos.find(p => p && p.id === photoId);
            if (foundInSlot) {
              const recovered = { ...foundInSlot, assignedBookId: null, assignedSlot: null };
              photoPool.push(recovered);
              selectedPoolPhotoId = recovered.id;
              break;
            }
          }
        }
      }
      removePhotoFromSlots(photoId);

      // Синхронизация отвязки слота с SQLite
      if (photoId && (photoId.startsWith('ast_') || photoId.startsWith('photo_'))) {
        try {
          fetch('/api/assets/assign', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ asset_id: photoId, slot: null })
          }).catch(e => {});
        } catch(e) {}
      }

      renderPool();
      renderBooksTabs();
      renderActiveBookSlots();
      scheduleAutoSave();
    }

    function removePhotoFromSlots(photoId) {
      booksSession.forEach(b => {
        if (b.slots.cover_front && b.slots.cover_front.id === photoId) b.slots.cover_front = null;
        ['cover_back', 'info_pages', 'illustrations', 'mantra_defects'].forEach(s => {
          if (Array.isArray(b.slots[s])) {
            b.slots[s] = b.slots[s].filter(p => p && p.id !== photoId);
          } else if (b.slots[s] && b.slots[s].id === photoId) {
            b.slots[s] = [];
          }
        });
      });
    }

    function clearCurrentBookSlots() {
      const book = getActiveBook();
      if (book.slots.cover_front) {
        book.slots.cover_front.assignedBookId = null;
        book.slots.cover_front.assignedSlot = null;
        book.slots.cover_front = null;
      }
      ['cover_back', 'info_pages', 'illustrations', 'mantra_defects'].forEach(s => {
        const list = Array.isArray(book.slots[s]) ? book.slots[s] : (book.slots[s] ? [book.slots[s]] : []);
        list.forEach(p => { p.assignedBookId = null; p.assignedSlot = null; });
        book.slots[s] = [];
      });
      // Также гарантируем сброс в photoPool для всех фото этой книги
      photoPool.forEach(p => {
        if (p.assignedBookId === book.id) {
          p.assignedBookId = null;
          p.assignedSlot = null;
        }
      });
      renderPool();
      renderBooksTabs();
      renderActiveBookSlots();
      scheduleAutoSave();
    }



// -------------------------------------------------------------
// ИИ-ВЫРЕЗАНИЕ ФОНА, СЛОТЫ И РАСКЛАДКА КНИГ
// -------------------------------------------------------------
    const aiProcessQueue = [];
    let activeAiWorkers = 0;
    const MAX_CONCURRENT_AI = 4;

    function queueAiBackgroundRemoval(photoId, force = false) {
      const photo = findPhotoById(photoId);
      if (!photo || photo.isAiProcessed || photo.isAiProcessing) return;

      // П. 3.2 спецификации: автоматическое вырезание стола разрешено ТОЛЬКО для обложки и задника!
      if (!force && photo.assignedSlot && !['cover_front', 'cover_back'].includes(photo.assignedSlot)) {
        return;
      }

      if (!aiProcessQueue.includes(photoId)) {
        aiProcessQueue.push(photoId);
      }
      processNextInAiQueue();
    }

    async function processNextInAiQueue() {
      if (activeAiWorkers >= MAX_CONCURRENT_AI || aiProcessQueue.length === 0) return;

      const photoId = aiProcessQueue.shift();
      const photo = findPhotoById(photoId);
      if (!photo || photo.isAiProcessed) {
        processNextInAiQueue();
        return;
      }

      activeAiWorkers++;
      try {
        await quickAiProcessPhoto(photoId, null, true);
      } catch (e) {
        console.error('Ошибка фонового вырезания фона для', photoId, e);
      } finally {
        activeAiWorkers--;
        processNextInAiQueue();
      }
    }

    function batchAiProcessAllPool() {
      const allPhotos = [];
      photoPool.forEach(p => { if (!p.isAiProcessed) allPhotos.push(p); });
      booksSession.forEach(b => {
        if (b.slots.cover_front && !b.slots.cover_front.isAiProcessed && !allPhotos.some(p => p.id === b.slots.cover_front.id)) {
          allPhotos.push(b.slots.cover_front);
        }
        ['cover_back', 'info_pages', 'illustrations', 'mantra_defects'].forEach(s => {
          const list = Array.isArray(b.slots[s]) ? b.slots[s] : (b.slots[s] ? [b.slots[s]] : []);
          list.forEach(p => {
            if (!p.isAiProcessed && !allPhotos.some(item => item.id === p.id)) {
              allPhotos.push(p);
            }
          });
        });
      });

      if (allPhotos.length === 0) {
        showToast('✨ Все фотографии уже обработаны нейросетью!');
        return;
      }

      showToast(`✨ Запущено фоновое вырезание фона для ${allPhotos.length} фото...`);
      allPhotos.forEach(p => queueAiBackgroundRemoval(p.id));
    }

    async function quickAiProcessPhoto(photoId, e, silent = false) {
      if (e) e.stopPropagation();
      const photo = findPhotoById(photoId);
      if (!photo || photo.isAiProcessing) return;

      photo.isAiProcessing = true;
      renderPool();
      renderActiveBookSlots();
      if (!silent) {
        showToast(`⏳ ИИ начал вырезание фона "${photo.name}"...`);
      }

      try {
        // Оптимизированный серверный путь для ассетов V2 (без передачи base64)
        if (photo.id && photo.id.startsWith('ast_')) {
          const aiResp = await fetch('/api/assets/run_ai', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ asset_id: photo.id })
          });
          const aiData = await aiResp.json();
          if (aiData.success) {
            photo.aiWhiteOriginal = `/api/assets/${photo.id}/full?t=${Date.now()}`;
            photo.preview = `/api/assets/${photo.id}/preview?t=${Date.now()}`;
            photo.isProcessed = true;
            photo.isAiProcessed = true;
            photo.isAiProcessing = false;
            let effectiveCropRel = photo.cropRelative || photo.aiCropRelative || aiData.crop_relative;
            if (effectiveCropRel) {
              photo.cropRelative = effectiveCropRel;
              photo.aiCropRelative = effectiveCropRel;
              photo.isCropped = true;
            }

            const rot = photo.rotation || 0;
            let croppedUrl = null;
            if (effectiveCropRel && typeof window.renderCroppedFromFullSourceAsync === 'function') {
              try {
                croppedUrl = await window.renderCroppedFromFullSourceAsync(photo.aiWhiteOriginal, rot, effectiveCropRel);
              } catch (err) {
                console.warn('Ошибка обрезки при быстром ИИ (ассет):', err);
              }
            } else if (effectiveCropRel && typeof window.cropImageSourceAsync === 'function') {
              try {
                croppedUrl = await window.cropImageSourceAsync(photo.aiWhiteOriginal, effectiveCropRel);
              } catch (err) {
                console.warn('Ошибка обрезки при быстром ИИ (ассет):', err);
              }
            }

            if (croppedUrl) {
              photo.croppedBase = croppedUrl;
              photo.preview = croppedUrl;
            }

            if (typeof initPhotoHistory === 'function') initPhotoHistory(photo);

            if (typeof currentEditingPhoto !== 'undefined' && currentEditingPhoto && currentEditingPhoto.id === photo.id && typeof isStudioOpen !== 'undefined' && isStudioOpen) {
              const displaySrc = photo.croppedBase || photo.aiWhiteOriginal;
              const displayType = photo.croppedBase ? 'cropped' : 'full';
              if (typeof reloadStudioCropper === 'function') {
                reloadStudioCropper(displaySrc, () => {
                  if (displayType === 'full' && rot !== 0 && typeof cropperInstance !== 'undefined' && cropperInstance) {
                    cropperInstance.rotateTo(rot);
                  }
                  if (typeof fitStudioImageToContainer === 'function') fitStudioImageToContainer(false);
                  if (typeof setStudioInteractionMode === 'function') setStudioInteractionMode('move');
                  if (typeof updateZoomBadge === 'function') updateZoomBadge();
                  if (typeof updateCropResolution === 'function') updateCropResolution();
                  if (typeof updateStudioHistoryUI === 'function') updateStudioHistoryUI();
                }, displayType);
              }
            }

            renderPool();
            renderActiveBookSlots();
            if (!silent) showToast(`✨ ИИ вырезал фон на чистый белый (rembg)!`);
            scheduleAutoSave();
            return;
          }
        }

        if (!photo.cameraOriginal) {
          photo.cameraOriginal = photo.rawOriginal || photo.preview;
        }
        if (!photo.rawOriginal) {
          photo.rawOriginal = photo.cameraOriginal;
        }
        const baseSrc = photo.cameraOriginal || photo.rawOriginal || photo.preview;
        const role = photo.assignedSlot || 'cover_front';
        const data = await ApiClient.processPhoto(baseSrc, role, true);
        if (!data.success || !data.image) {
          throw new Error(data.error || 'Ошибка ИИ-обработки');
        }

        if (typeof initPhotoHistory === 'function') {
          initPhotoHistory(photo);
        }

        photo.aiWhiteOriginal = data.image;
        photo.isProcessed = true;
        photo.isAiProcessed = true;

        // Сохраняем или определяем рамку кадрирования
        let effectiveCropRel = photo.cropRelative || photo.aiCropRelative || data.crop_relative;
        if (effectiveCropRel) {
          photo.cropRelative = effectiveCropRel;
          photo.aiCropRelative = effectiveCropRel;
        }

        // Если рамка есть, сразу нарезаем новое изображение с белым фоном с учетом текущего угла поворота
        const rot = photo.rotation || 0;
        let croppedUrl = null;
        if (effectiveCropRel && typeof window.renderCroppedFromFullSourceAsync === 'function') {
          try {
            croppedUrl = await window.renderCroppedFromFullSourceAsync(data.image, rot, effectiveCropRel);
          } catch (err) {
            console.warn('Ошибка обрезки при быстром ИИ:', err);
          }
        } else if (effectiveCropRel && typeof window.cropImageSourceAsync === 'function') {
          try {
            croppedUrl = await window.cropImageSourceAsync(data.image, effectiveCropRel);
          } catch (err) {
            console.warn('Ошибка обрезки при быстром ИИ:', err);
          }
        }

        if (croppedUrl) {
          photo.croppedBase = croppedUrl;
          photo.isCropped = true;
        }

        let previewBase = photo.croppedBase || data.image;
        if (!photo.croppedBase && Math.abs(rot) > 0.05 && typeof window.renderCroppedFromFullSourceAsync === 'function') {
          try {
            previewBase = await window.renderCroppedFromFullSourceAsync(data.image, rot, null);
          } catch (err) {}
        }

        const filters = {
          whiten: photo.whiten || 0,
          brightness: photo.brightness || 0,
          contrast: photo.contrast || 0,
          saturation: photo.saturation || 0
        };

        let filteredUrl = previewBase;
        if (typeof window.applyFiltersToImageAsync === 'function') {
          filteredUrl = await window.applyFiltersToImageAsync(previewBase, filters);
        }

        photo.preview = filteredUrl;
        photo.data = filteredUrl.includes(',') ? filteredUrl.split(',')[1] : filteredUrl;
        photo.mime = 'image/jpeg';
        photo.is_s3_uploaded = false;
        photo.s3_url = null;

        // Добавляем шаг истории без затирания предыдущих действий
        if (!Array.isArray(photo.history)) photo.history = [];
        photo.history.push({
          label: 'ИИ белый фон (rembg)',
          timestamp: Date.now(),
          preview: photo.preview,
          data: photo.data,
          croppedBase: photo.croppedBase || null,
          rawOriginal: photo.rawOriginal,
          cameraOriginal: photo.cameraOriginal,
          aiWhiteOriginal: photo.aiWhiteOriginal,
          isCropped: Boolean(photo.isCropped),
          isAiProcessed: true,
          inCropMode: false,
          hasCropBox: Boolean(photo.isCropped),
          cropBoxOnOriginal: photo.cropBoxOnOriginal || null,
          cropRelative: photo.cropRelative ? { ...photo.cropRelative } : null,
          cropRatio: 'none',
          whiten: photo.whiten || 0,
          brightness: photo.brightness || 0,
          contrast: photo.contrast || 0,
          saturation: photo.saturation || 0,
          rotation: rot,
          cardinal: Math.round(rot / 90) * 90 % 360
        });
        photo.historyIndex = photo.history.length - 1;

        if (typeof currentEditingPhoto !== 'undefined' && currentEditingPhoto && currentEditingPhoto.id === photo.id && typeof isStudioOpen !== 'undefined' && isStudioOpen) {
          const displaySrc = photo.croppedBase || data.image;
          const displayType = photo.croppedBase ? 'cropped' : 'full';
          if (typeof reloadStudioCropper === 'function') {
            reloadStudioCropper(displaySrc, () => {
              if (displayType === 'full' && rot !== 0 && typeof cropperInstance !== 'undefined' && cropperInstance) {
                cropperInstance.rotateTo(rot);
              }
              if (typeof fitStudioImageToContainer === 'function') fitStudioImageToContainer(false);
              if (typeof setStudioInteractionMode === 'function') setStudioInteractionMode('move');
              if (typeof updateZoomBadge === 'function') updateZoomBadge();
              if (typeof updateCropResolution === 'function') updateCropResolution();
              if (typeof updateStudioHistoryUI === 'function') updateStudioHistoryUI();
            }, displayType);
          }
        }

        if (!silent) {
          showToast(`✨ Кадр "${photo.name}": фон вырезан, рамка готова!`);
        }
      } catch (err) {
        if (!silent) {
          showToast(`❌ Ошибка ИИ: ${err.message}`, 4000);
        }
      } finally {
        photo.isAiProcessing = false;
        renderPool();
        renderActiveBookSlots();
        scheduleAutoSave();
      }
    }

    function renderActiveBookSlots() {

      const book = getActiveBook();

      // Одиночные слоты (Передняя и Задняя обложка)
      const renderSingle = (slotId, photo, placeholderText) => {
        const el = document.getElementById(slotId);
        if (!photo) {
          el.innerHTML = `
            <div class="flex flex-col items-center justify-center text-center p-4 min-h-[190px] w-full text-slate-500">
              <span class="text-2xl mb-1.5 opacity-50">${slotId === 'slot_cover_front' ? '🌟' : '🔄'}</span>
              <span class="text-xs font-medium leading-relaxed">${placeholderText}</span>
            </div>
          `;
          return;
        }
        const processed = isPhotoProcessed(photo);
        const isThisBookRecognizing = Boolean(book && book.isAiRecognizing);
        const isPhotoBusy = Boolean(photo.isAiProcessing || photo.isProcessing);
        const isBusy = Boolean(isThisBookRecognizing || isPhotoBusy);

        el.innerHTML = `
          <div class="relative w-full h-full min-h-[190px] group rounded-xl overflow-hidden border border-slate-700 bg-slate-950 flex flex-col justify-between p-1.5 shadow-md transition-all cursor-grab active:cursor-grabbing select-none hover:border-amber-400 ${isBusy ? 'opacity-90 select-none' : ''}"
               draggable="${!isBusy}" ondragstart="handlePhotoDragStart(event, '${photo.id}', '${slotId}')" ondragend="handlePhotoDragEnd(event)">
            
            <!-- ВЕРХНЯЯ СТРОКА: СТАТУС ОБРАБОТКИ И БЫСТРЫЕ КНОПКИ -->
            <div class="flex items-center justify-between gap-1 mb-1 z-30" ondblclick="event.stopPropagation()">
              <div class="flex items-center gap-1">
                ${isBusy ? `
                  <span class="px-2 py-0.5 rounded ${isThisBookRecognizing ? 'bg-amber-500' : 'bg-violet-600'} text-slate-950 font-black text-[9px] animate-pulse shadow">${isThisBookRecognizing ? '⏳ АНАЛИЗ...' : '⏳ ОБРАБОТКА...'}</span>
                ` : (processed ? `
                  <span class="px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold text-[9px] shadow flex items-center gap-1" title="Финальная версия готова к публикации на Ozon">
                    <span>✅</span> <span>ГОТОВО К OZON</span>
                  </span>
                ` : `
                  <span class="px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30 font-bold text-[9px] shadow flex items-center gap-1" title="Исходный снимок без обрезки и фильтров">
                    <span>📷</span> <span>ИСХОДНИК</span>
                  </span>
                `)}
                ${photo.isCropped ? '<span class="px-1.5 py-0.2 rounded bg-slate-850 text-slate-300 border border-slate-750 text-[8px]" title="Кадрировано под пропорции">✂️ КРОП</span>' : ''}
                ${(photo.s3_url || photo.is_s3_uploaded) ? '<span class="px-1.5 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800 text-[9px] font-bold shadow" title="Выгружено в Yandex S3 CDN">☁️ S3</span>' : ''}
                <span class="px-1.5 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800 text-[8px] font-bold shadow" title="Главное фото витрины Ozon">🌐 OZON</span>
                ${photo.status === 'ERROR' ? `<span class="px-1.5 py-0.5 rounded bg-rose-950 text-rose-300 border border-rose-700 text-[9px] font-bold shadow cursor-pointer" onclick="quickAiProcessPhoto('${photo.id}', event)" title="Ошибка обработки. Кликните для повтора">⚠️ СБОЙ</span>` : ''}
              </div>
              <div class="flex items-center gap-0.5 bg-black/90 p-0.5 rounded-lg shadow backdrop-blur-xs border border-slate-700/60">
                <button type="button" onclick="inspectPhotoLightbox('${photo.id}', event)" class="p-1 rounded hover:bg-sky-600 hover:text-white text-sky-300 text-xs transition" title="👁️ Быстрый просмотр 1:1 (как в Ozon)">👁️</button>
                <button type="button" onclick="quickAiProcessPhoto('${photo.id}', event)" class="p-1 rounded hover:bg-violet-600 hover:text-white text-violet-300 text-xs transition" title="✨ ИИ-вырезание фона на чистый белый Ozon (rembg)">✨</button>
                <button type="button" onclick="openPhotoStudio('${photo.id}', event)" class="p-1 rounded hover:bg-amber-500 hover:text-black text-amber-300 text-xs transition" title="✏️ Редактор (кадрирование, фильтры)">✏️</button>
                ${(photo.cameraOriginal || photo.isAiProcessed || processed || photo.isCropped || (photo.history && photo.historyIndex > 0)) ? `<button type="button" onclick="revertPhotoToOriginal('${photo.id}', event)" class="p-1 rounded bg-rose-950/60 hover:bg-rose-900 border border-rose-700/50 text-rose-300 hover:text-white text-xs transition flex items-center justify-center shadow-xs" title="↩️ Вернуть исходное фото с камеры (1 шаг)">↩️</button>` : ''}
                <button type="button" onclick="unassignPhoto('${photo.id}', event)" class="p-1 rounded hover:bg-rose-600 hover:text-white text-rose-400 text-xs transition" title="Убрать из книги в общий пул">✕</button>
              </div>
            </div>

            <!-- БОЛЬШАЯ КАРТИНКА КНИГИ (ВЫСОТА 176px) В РЕЖИМЕ OBJECT-CONTAIN (ЧЕСТНЫЕ ГРАНИЦЫ И МАСШТАБ) -->
            <div class="relative w-full h-44 rounded-lg overflow-hidden bg-slate-950/80 border border-slate-800 flex items-center justify-center p-1.5 cursor-pointer shadow-inner"
                 ondblclick="openPhotoStudio('${photo.id}', event)" title="Двойной клик по картинке — открыть фоторедактор">
              <img src="${getPhotoDisplayUrl(photo)}" class="max-w-full max-h-full object-contain pointer-events-none drop-shadow select-none transition-transform duration-200" loading="lazy" onerror="const alt='${photo.url || photo.s3_url || photo.preview || photo.cameraOriginal || ''}'; if(alt && this.src!==alt) this.src=alt;">

              <!-- ФИКСИРОВАННАЯ КНОПКА РАЗВОРОТА НА 90° В ПРАВОМ ВЕРХНЕМ УГЛУ КАРТИНКИ -->
              <button type="button" onclick="quickRotatePhoto('${photo.id}', 90, event)" ondblclick="event.stopPropagation()" class="absolute top-2 right-2 w-8 h-8 rounded-lg bg-black/85 hover:bg-amber-500 hover:text-black text-amber-300 border border-slate-700/80 shadow-md flex items-center justify-center text-xs transition active:scale-90 z-10" title="Повернуть на 90° (всегда на этом месте)">🔄</button>

              <!-- БЛОКИРОВКА И СПИННЕР ПРИ ОБРАБОТКЕ -->
              ${isBusy ? `
                <div class="absolute inset-0 bg-slate-950/70 backdrop-blur-xs flex flex-col items-center justify-center gap-2 z-20 pointer-events-none select-none">
                  <div class="w-8 h-8 border-3 ${isThisBookRecognizing ? 'border-amber-400' : 'border-violet-400'} border-t-transparent rounded-full animate-spin"></div>
                  <span class="text-[10px] font-bold ${isThisBookRecognizing ? 'text-amber-300' : 'text-violet-300'} tracking-wide animate-pulse">
                    ${isThisBookRecognizing ? 'Анализ Gemini...' : (photo.isAiProcessing ? 'ИИ вырезает...' : 'Отбеливание...')}
                  </span>
                </div>
              ` : ''}
            </div>

            <!-- ПОДВАЛ: ИМЯ ФАЙЛА И ПЕРЕМЕЩЕНИЕ В ДРУГУЮ КАТЕГОРИЮ -->
            <div class="mt-1 pt-1 border-t border-slate-850 flex items-center justify-between text-[10px]" ondblclick="event.stopPropagation()">
              <span class="font-mono text-slate-400 truncate max-w-[120px]" title="${photo.name}">${photo.name}</span>
              <button type="button" onclick="promptMovePhoto('${photo.id}', event)" class="text-[10px] text-amber-400 hover:text-amber-300 font-semibold" title="Переместить в другой слот книги">🔀 Сменить...</button>
            </div>
          </div>
        `;
      };

      const slots = (book && book.slots) ? book.slots : {};
      renderSingle('slot_cover_front', slots.cover_front, 'Перетащите сюда фото обложки или нажмите [1]');

      // Множественные слоты (Задник, Титул, Иллюстрации, Дефекты)
      const renderMulti = (slotId, photos, placeholderText) => {
        const el = document.getElementById(slotId);
        if (!photos || photos.length === 0) {
          const icon = slotId === 'slot_info_pages' ? '📄' : (slotId === 'slot_illustrations' ? '🎨' : (slotId === 'slot_cover_back' ? '🔄' : '⚠️'));
          el.innerHTML = `
            <div class="col-span-full flex flex-col items-center justify-center text-center p-4 min-h-[190px] w-full text-slate-500">
              <span class="text-2xl mb-1.5 opacity-50">${icon}</span>
              <span class="text-xs font-medium leading-relaxed">${placeholderText}</span>
            </div>
          `;
          return;
        }
        el.innerHTML = photos.map((p, idx) => {
          const processed = isPhotoProcessed(p);
          const isThisBookRecognizing = Boolean(book && book.isAiRecognizing);
          const isPhotoBusy = Boolean(p.isAiProcessing || p.isProcessing);
          const isBusy = Boolean(isThisBookRecognizing || isPhotoBusy);

          return `
            <div class="relative group rounded-xl overflow-hidden bg-slate-950 border border-slate-700/80 p-1 flex flex-col justify-between shadow-md transition-all cursor-grab active:cursor-grabbing select-none hover:border-amber-400 ${isBusy ? 'opacity-90 select-none' : ''}"
                 draggable="${!isBusy}" ondragstart="handlePhotoDragStart(event, '${p.id}', '${slotId}')" ondragend="handlePhotoDragEnd(event)">

              
              <!-- ВЕРХ КАРТОЧКИ: НОМЕР И СТАТУС -->
              <div class="flex items-center justify-between gap-1 mb-1 z-30" ondblclick="event.stopPropagation()">
                <div class="flex items-center gap-1">
                  <span class="px-1.5 py-0.2 rounded bg-black/80 text-[9px] font-mono font-bold text-white">#${idx+1}</span>
                  ${isBusy ? `
                    <span class="px-1 py-0.2 rounded ${isThisBookRecognizing ? 'bg-amber-500' : 'bg-violet-600'} text-slate-950 font-black text-[8px] animate-pulse shadow">${isThisBookRecognizing ? '⏳ АНАЛИЗ...' : '⏳ ИИ...'}</span>
                  ` : (processed ? `
                    <span class="px-1.5 py-0.2 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold text-[8px] shadow flex items-center gap-1" title="Финальная версия готова к публикации на Ozon">
                      <span>✅</span> <span>ГОТОВО К OZON</span>
                    </span>
                  ` : `
                    <span class="px-1.5 py-0.2 rounded-full bg-amber-500/15 text-amber-300 border border-amber-500/30 font-bold text-[8px] shadow flex items-center gap-1" title="Исходный снимок без обрезки и фильтров">
                      <span>📷</span> <span>ИСХОДНИК</span>
                    </span>
                  `)}
                  ${p.isCropped ? '<span class="px-1 py-0.2 rounded bg-slate-850 text-slate-300 border border-slate-750 text-[8px]" title="Кадрировано под пропорции">✂️ КРОП</span>' : ''}
                  ${(p.s3_url || p.is_s3_uploaded) ? '<span class="px-1 py-0.2 rounded bg-sky-950 text-sky-400 border border-sky-800 text-[8px] font-bold shadow" title="Выгружено в Yandex S3 CDN">☁️ S3</span>' : ''}
                  ${slotId === 'slot_info_pages' ? `
                    <span class="px-1.5 py-0.2 rounded bg-amber-950 text-amber-300 border border-amber-600/70 font-bold text-[8px] shadow" title="Фото титульного листа для ИИ распознавания. Сохраняется в архив и НЕ отправляется покупателям на Ozon.">🔒 ТОЛЬКО ИИ (НЕ НА OZON)</span>
                  ` : `
                    <span class="px-1 py-0.2 rounded bg-sky-950 text-sky-400 border border-sky-800 text-[8px] font-bold shadow" title="Это фото выгружается в карточку товара на Ozon">🌐 OZON</span>
                  `}
                  ${p.status === 'ERROR' ? `<span class="px-1 py-0.2 rounded bg-rose-950 text-rose-300 border border-rose-700 text-[8px] font-bold shadow cursor-pointer" onclick="quickAiProcessPhoto('${p.id}', event)" title="Ошибка обработки. Кликните для повтора">⚠️</span>` : ''}
                </div>
                <div class="flex items-center gap-0.5 bg-black/85 p-0.5 rounded shadow border border-slate-700/60">
                  <button type="button" onclick="inspectPhotoLightbox('${p.id}', event)" class="p-0.5 rounded hover:bg-sky-600 hover:text-white text-sky-300 text-[10px] transition" title="👁️ Быстрый просмотр 1:1 (как в Ozon)">👁️</button>
                  <button type="button" onclick="quickAiProcessPhoto('${p.id}', event)" class="p-0.5 rounded hover:bg-violet-600 hover:text-white text-violet-300 text-[10px] transition" title="✨ ИИ-вырезание фона на чистый белый Ozon (rembg)">✨</button>
                  <button type="button" onclick="openPhotoStudio('${p.id}', event)" class="p-0.5 rounded hover:bg-amber-500 hover:text-black text-amber-300 text-[10px] transition" title="Редактор">✏️</button>
                  ${(p.cameraOriginal || p.isAiProcessed || processed || p.isCropped || (p.history && p.historyIndex > 0)) ? `<button type="button" onclick="revertPhotoToOriginal('${p.id}', event)" class="p-0.5 rounded bg-rose-950/60 hover:bg-rose-900 border border-rose-700/50 text-rose-300 hover:text-white text-[10px] transition" title="↩️ Вернуть исходное фото с камеры (1 шаг)">↩️</button>` : ''}
                  <button type="button" onclick="unassignPhoto('${p.id}', event)" class="p-0.5 rounded hover:bg-rose-600 hover:text-white text-rose-400 text-[10px] transition" title="Убрать в пул">✕</button>
                </div>
              </div>


              <!-- КАРТИНКА (ВЫСОТА 144px) В РЕЖИМЕ OBJECT-CONTAIN (ЧЕСТНЫЕ ГРАНИЦЫ И МАСШТАБ) -->
              <div class="relative w-full h-36 rounded-lg overflow-hidden bg-slate-950/80 border border-slate-800 flex items-center justify-center p-1.5 cursor-pointer shadow-inner"
                   ondblclick="openPhotoStudio('${p.id}', event)" title="Двойной клик по картинке — открыть фоторедактор">
                <img src="${getPhotoDisplayUrl(p)}" class="max-w-full max-h-full object-contain pointer-events-none drop-shadow select-none transition-transform duration-200" loading="lazy" onerror="const alt='${p.url || p.s3_url || p.preview || p.cameraOriginal || ''}'; if(alt && this.src!==alt) this.src=alt;">

                <!-- ФИКСИРОВАННАЯ КНОПКА РАЗВОРОТА НА 90° В ПРАВОМ ВЕРХНЕМ УГЛУ КАРТИНКИ -->
                <button type="button" onclick="quickRotatePhoto('${p.id}', 90, event)" ondblclick="event.stopPropagation()" class="absolute top-1.5 right-1.5 w-7 h-7 rounded-lg bg-black/85 hover:bg-amber-500 hover:text-black text-amber-300 border border-slate-700/80 shadow flex items-center justify-center text-xs transition active:scale-90 z-10" title="Повернуть на 90° (всегда на этом месте)">🔄</button>

                <!-- БЛОКИРОВКА И СПИННЕР ПРИ ОБРАБОТКЕ -->
                ${isBusy ? `
                  <div class="absolute inset-0 bg-slate-950/70 backdrop-blur-xs flex flex-col items-center justify-center gap-2 z-20 pointer-events-none select-none">
                    <div class="w-7 h-7 border-3 ${isThisBookRecognizing ? 'border-amber-400' : 'border-violet-400'} border-t-transparent rounded-full animate-spin"></div>
                    <span class="text-[9px] font-bold ${isThisBookRecognizing ? 'text-amber-300' : 'text-violet-300'} tracking-wide animate-pulse">
                      ${isThisBookRecognizing ? 'Анализ...' : (p.isAiProcessing ? 'ИИ вырезает...' : 'Отбеливание...')}
                    </span>
                  </div>
                ` : ''}
              </div>

              <!-- ПОДВАЛ МИНИАТЮРЫ -->
              <div class="mt-1 flex items-center justify-between text-[9px] font-mono text-slate-400 px-0.5" ondblclick="event.stopPropagation()">
                <span class="truncate max-w-[85px]" title="${p.name}">${p.name}</span>
                <button type="button" onclick="promptMovePhoto('${p.id}', event)" class="text-amber-400 hover:text-amber-300 font-sans font-semibold text-[9px]">🔀</button>
              </div>
            </div>
          `;
        }).join('');
      };

      const backPhotos = Array.isArray(slots.cover_back) ? slots.cover_back : (slots.cover_back ? [slots.cover_back] : []);
      renderMulti('slot_cover_back', backPhotos, 'Перетащите задник книги (или нескольких) или нажмите [2]');
      renderMulti('slot_info_pages', slots.info_pages, 'Перетащите титул / оборот / колофон (ИИ считает данные) или нажмите [3]');
      renderMulti('slot_illustrations', slots.illustrations, 'Перетащите иллюстрации и развороты сюда или нажмите [4]');
      renderMulti('slot_mantra_defects', slots.mantra_defects, 'Только фото повреждений (надрывы, пометки) или нажмите [5]');

      // Синхронизируем обязательную плашку-предупреждение в аннотации в зависимости от слота [5. Дефекты]
      syncAnnotationWarningWithDefectsSlot();
    }

    function syncAnnotationWarningWithDefectsSlot() {
      const book = getActiveBook();
      const antEl = document.getElementById('annotation');
      const hintEl = document.getElementById('annotationNoticeHint');
      if (!antEl || !book) return;
      if (!book.formData) book.formData = {};

      const defectCount = (book.slots && book.slots.mantra_defects) ? book.slots.mantra_defects.length : 0;
      const hasMantraDefects = defectCount > 0;

      // Источник аннотации: берем строго из book.formData.annotation текущей книги, если сохранено
      const baseText = (book.formData.annotation !== undefined && book.formData.annotation !== null)
        ? String(book.formData.annotation)
        : antEl.value;

      let cleanText = cleanAnnotationText(baseText);

      const isManual = Boolean(book.formData && book.formData.is_manual_condition);
      const currentCond = book.formData.condition || (document.getElementById('condition')?.value) || 'Очень хорошая';

      let shouldHaveWarning = hasMantraDefects;
      if (!hasMantraDefects && isManual && (currentCond === 'Хорошая' || currentCond === 'Удовлетворительная')) {
        shouldHaveWarning = true;
      }

      let finalValue = cleanText;
      if (shouldHaveWarning && cleanText) {
        finalValue = ANNOTATION_WARNING + '\n\n' + cleanText;
      }

      if (antEl.value !== finalValue) {
        antEl.value = finalValue;
        antEl.classList.add('field-updated');
        setTimeout(() => antEl.classList.remove('field-updated'), 600);
      }
      book.formData.annotation = finalValue;

      // Авто-синхронизация сохранности книги по регламенту:
      // 1. При наличии дефектов — состояние минимум «Хорошая» (или ручная «Удовлетворительная»).
      // 2. Без дефектов по умолчанию «Очень хорошее», но сохраняется ручной выбор букиниста («Хорошая»/«Удовлетворительная»).
      if (typeof setCondition === 'function') {
        if (hasMantraDefects) {
          if (currentCond === 'Удовлетворительная') {
            setCondition('Удовлетворительная', false);
          } else {
            setCondition('Хорошая', false);
          }
        } else {
          if (isManual && (currentCond === 'Хорошая' || currentCond === 'Удовлетворительная')) {
            setCondition(currentCond, false);
          } else {
            setCondition('Очень хорошая', false);
          }
        }
      }

      if (hintEl) {
        if (hasMantraDefects) {
          const condName = (book.formData && book.formData.condition === 'Удовлетворительная') ? 'Удовлетворительное' : 'Хорошее';
          hintEl.className = 'text-xs text-amber-400 mt-1.5 font-medium flex items-center gap-1.5';
          hintEl.innerHTML = `<span>⚠️</span> <span>В слоте [5. Дефекты] фото (${defectCount} шт.). Предупреждение добавлено в аннотацию, сохранность: <b>${condName}</b>.</span>`;
        } else if (isManual && (currentCond === 'Хорошая' || currentCond === 'Удовлетворительная')) {
          hintEl.className = 'text-xs text-amber-400 mt-1.5 font-medium flex items-center gap-1.5';
          hintEl.innerHTML = `<span>💡</span> <span>Сохранность вручную: <b>${currentCond}</b>. Предупреждение добавлено в аннотацию.</span>`;
        } else {
          hintEl.className = 'text-xs text-emerald-400 mt-1.5 font-medium flex items-center gap-1.5';
          hintEl.innerHTML = `<span>✓</span> <span>Слот [5. Дефекты] пуст. Сохранность: <b>Очень хорошее</b>. Предупреждение отключено.</span>`;
        }
      }
    }

    // -------------------------------------------------------------
    // DRAG AND DROP: МЕЖДУ СЛОТАМИ, ИЗ ПУЛА В СЛОТЫ И ОБРАТНО В ПУЛ
    // -------------------------------------------------------------
    // draggedPhotoId и draggedSourceSlot объявлены в state.js
    draggedPhotoId = null;
    draggedSourceSlot = null;

    function handlePhotoDragStart(e, photoId, sourceSlot) {
      draggedPhotoId = photoId;
      draggedSourceSlot = sourceSlot || 'pool';
      e.dataTransfer.setData('text/plain', photoId);
      e.dataTransfer.setData('source-slot', draggedSourceSlot);
      e.dataTransfer.effectAllowed = 'move';
      if (e.currentTarget) e.currentTarget.classList.add('photo-dragging');
    }

    function handlePhotoDragEnd(e) {
      if (e.currentTarget) e.currentTarget.classList.remove('photo-dragging');
      document.querySelectorAll('.drag-over').forEach(el => el.classList.remove('drag-over'));
      draggedPhotoId = null;
      draggedSourceSlot = null;
    }

    function allowDrop(e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      const card = e.currentTarget.closest('.slot-card') || e.currentTarget;
      if (card) card.classList.add('drag-over');
    }

    function dragLeave(e) {
      const card = e.currentTarget.closest('.slot-card') || e.currentTarget;
      if (card) card.classList.remove('drag-over');
    }

    function handleDrop(e, targetSlot) {
      e.preventDefault();
      const card = e.currentTarget.closest('.slot-card') || e.currentTarget;
      if (card) card.classList.remove('drag-over');
      const photoId = e.dataTransfer.getData('text/plain') || draggedPhotoId;
      if (!photoId) return;
      assignPhotoToSlot(photoId, targetSlot);
    }

    function allowPoolDrop(e) {
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      const pool = document.getElementById('poolContainer');
      if (pool) pool.classList.add('drag-over');
    }

    function dragLeavePool(e) {
      const pool = document.getElementById('poolContainer');
      if (pool) pool.classList.remove('drag-over');
    }

    function handlePoolDrop(e) {
      e.preventDefault();
      const pool = document.getElementById('poolContainer');
      if (pool) pool.classList.remove('drag-over');
      const photoId = e.dataTransfer.getData('text/plain') || draggedPhotoId;
      if (!photoId) return;
      unassignPhoto(photoId);
    }

    function promptMovePhoto(photoId, e) {
      if (e) e.stopPropagation();
      const photo = findPhotoById(photoId);
      if (!photo) return;
      const slotNames = [
        '1: Обложка (перед)',
        '2: Обложка (зад)',
        '3: Титул и выходные (ИИ)',
        '4: Иллюстрации',
        '5: Дефекты и нюансы',
        '0: Вернуть в свободный пул'
      ];
      const ans = prompt(`Куда переместить фото «${photo.name}»?\\n\\n` + slotNames.join('\\n') + '\\n\\nВведите цифру от 0 до 5:');
      if (ans === null) return;
      const map = {
        '1': 'cover_front',
        '2': 'cover_back',
        '3': 'info_pages',
        '4': 'illustrations',
        '5': 'mantra_defects'
      };
      if (ans.trim() === '0') {
        unassignPhoto(photoId);
      } else if (map[ans.trim()]) {
        assignPhotoToSlot(photoId, map[ans.trim()]);
      }
    }

    // -------------------------------------------------------------
    // ПАРАЛЛЕЛЬНЫЙ АВТО-КОНВЕЙЕР И ОЧЕРЕДЬ РАСПОЗНАВАНИЯ GEMINI VISION
    // -------------------------------------------------------------
    const bookAiQueue = [];
    let activeBookAiWorkers = 0;
    const MAX_CONCURRENT_BOOK_AI = 2;

    function queueBookAiRecognition(bookId) {
      const book = booksSession.find(b => b.id === bookId);
      if (!book || book.isAiRecognizing || book.isAiRecognized) return;
      if (!bookAiQueue.includes(bookId)) {
        bookAiQueue.push(bookId);
      }
      processNextBookInAiQueue();
    }

    async function processNextBookInAiQueue() {
      if (activeBookAiWorkers >= MAX_CONCURRENT_BOOK_AI || bookAiQueue.length === 0) return;

      const bookId = bookAiQueue.shift();
      const book = booksSession.find(b => b.id === bookId);
      if (!book || book.isAiRecognized) {
        processNextBookInAiQueue();
        return;
      }

      activeBookAiWorkers++;
      try {
        await runAiForBook(bookId, true);
      } catch (e) {
        console.error('Ошибка фонового распознавания книги', bookId, e);
      } finally {
        activeBookAiWorkers--;
        processNextBookInAiQueue();
      }
    }

    async function runAiForBook(targetBookId, silent = false) {
      const book = booksSession.find(b => b.id === targetBookId);
      if (!book || book.isAiRecognizing) return;

      const sendImages = [];
      const addCleanImg = (role, photo) => {
        if (!photo) return;
        let d = photo.data || photo.preview || photo.croppedBase || photo.cameraOriginal;
        if (!d) return;
        if (typeof d === 'string' && d.startsWith('data:') && d.includes(',')) {
          d = d.split(',')[1];
        }
        sendImages.push({ role_name: role, mime: photo.mime || 'image/jpeg', data: d });
      };

      if (book.slots.cover_front) addCleanImg("Передняя часть обложки", book.slots.cover_front);
      const backList = Array.isArray(book.slots.cover_back) ? book.slots.cover_back : (book.slots.cover_back ? [book.slots.cover_back] : []);
      backList.forEach((p, idx) => addCleanImg(backList.length > 1 ? `Вид обложки сзади #${idx+1}` : "Вид обложки сзади", p));
      book.slots.info_pages.forEach((p, idx) => addCleanImg(`Лист с информацией и описанием (титул/оборот #${idx+1})`, p));

      // Согласно п. 4.1 спецификации: фото иллюстраций и повреждений в Gemini не отправляются,
      // вместо этого передаются логические флаги для библиографического обогащения
      const hasIllustrations = Boolean(book.slots.illustrations && book.slots.illustrations.length > 0);
      const hasDefects = Boolean(book.slots.mantra_defects && book.slots.mantra_defects.length > 0);

      if (sendImages.length === 0) {
        if (!silent) alert('⚠️ В слотах этой книги нет фото для распознавания!');
        return;
      }

      if (!currentApiKey) {
        await loadSavedKey();
      }
      if (!currentApiKey) {
        if (!silent) openKeyModal();
        return;
      }

      book.isAiRecognizing = true;
      renderBooksTabs();
      if (book.id === window.activeBookId) {
        window.isBookAiRecognizing = true;
        renderActiveBookSlots();
        if (typeof window.updateAiBatchBtnState === 'function') window.updateAiBatchBtnState();
      }

      try {
        const result = await ApiClient.recognizeBook(sendImages, currentApiKey, hasIllustrations);
        if (!result.success) throw new Error(result.error || 'Ошибка распознавания');

        const recognizedData = result.data || {};

        // Заполняем данные через populateFields: для активной книги обновятся инпуты на экране,
        // для фоновой книги в book.formData запишутся проверенные бренды Ozon, жанры и ISBN без перекрытия экрана
        populateFields(recognizedData, book);

        if (book.id === window.activeBookId) {
          const fs = document.getElementById('formStatus');
          if (fs) {
            const verifiedBadge = recognizedData.verified_by ? ` (🌐 ${recognizedData.verified_by})` : '';
            fs.textContent = `✓ Данные книги «${recognizedData.title || 'Без названия'}» успешно внесены в форму!${verifiedBadge}`;
            fs.className = 'text-center text-xs text-emerald-400 font-semibold';
          }
        }

        book.isAiRecognized = true;
        const art = (book.formData && book.formData.article) || book.article || `Книга #${book.id}`;
        showToast(`✨ ИИ заполнил данные книги [${art}] «${recognizedData.title || 'Книга'}»${book.id !== window.activeBookId ? ' в фоне' : ''}!`);
        updatePipelineStatus(`✓ Книга [${art}] «${(recognizedData.title || '').substring(0, 30)}» заполнена ИИ`);
      } catch (err) {
        console.error(`Ошибка ИИ для книги ${book.id}:`, err);
        if (!silent) {
          const msg = err.message || '';
          if (msg.includes('503') || msg.includes('high demand') || msg.includes('UNAVAILABLE')) {
            alert('⚠️ Сервера Google Gemini сейчас испытывают пик нагрузки. Нажмите кнопку еще раз через несколько секунд.');
          } else if (msg.includes('429')) {
            alert('⚠️ Превышен лимит запросов Gemini API в минуту. Подождите 20-30 секунд и повторите.');
          } else {
            alert('Ошибка при распознавании:\n' + msg);
          }
        }
      } finally {
        book.isAiRecognizing = false;
        const curActive = typeof window.getActiveBook === 'function' ? window.getActiveBook() : null;
        window.isBookAiRecognizing = Boolean(curActive && curActive.isAiRecognizing);

        if (curActive && curActive.id === book.id) {
          renderActiveBookSlots();
        }
        if (typeof window.updateAiBatchBtnState === 'function') {
          window.updateAiBatchBtnState();
        }
        renderBooksTabs();
        scheduleAutoSave();
      }
    }

    async function runAiForActiveBook() {
      if (isStudioOpen && currentEditingPhoto && cropperInstance) {
        saveStudioChanges(null, true);
      }
      const cur = getActiveBook();
      if (!cur) return;
      await runAiForBook(cur.id, false);
    }

    async function runBatchDistributePipeline(silent = false) {
      const unassigned = photoPool.filter(p => !p.assignedBookId);
      if (unassigned.length === 0) {
        if (!silent) showToast('ℹ️ В пуле нет свободных фотографий для раскладки');
        return;
      }

      const perBookSelect = document.getElementById('batchPhotosPerBook');
      const schemeVal = perBookSelect ? perBookSelect.value : 'smart_ai';

      const startArtInput = document.getElementById('batchStartArticle');
      let startArtVal = startArtInput ? startArtInput.value.trim() : '';
      if (!startArtVal) {
        startArtVal = await calculateNextArticle(0);
        if (startArtInput) startArtInput.value = startArtVal;
      }

      const matchNum = startArtVal.match(/\d+/);
      let currentNum = matchNum ? parseInt(matchNum[0], 10) : 1;

      const statusBox = document.getElementById('batchPipelineStatus');
      const statusText = document.getElementById('batchPipelineStatusText');
      const statusCounter = document.getElementById('batchPipelineCounter');
      if (statusBox) statusBox.classList.remove('hidden');
      if (statusText) statusText.textContent = '⏳ Анализ пачки и распределение по книгам...';

      // 1. Проверяем, есть ли явная разметка по книгам со смартфона (Вариант 1)
      const uniqueMobileBooks = new Set(unassigned.map(p => p.bookIndex).filter(Boolean));
      let bookGroups = []; // Массив массивов объектов { photo, role }

      if (uniqueMobileBooks.size > 1) {
        // Оператор разделял книги на телефоне кнопкой «+ След. книга»!
        const groupedByMobile = {};
        unassigned.forEach(p => {
          const bIdx = p.bookIndex || 1;
          if (!groupedByMobile[bIdx]) groupedByMobile[bIdx] = [];
          groupedByMobile[bIdx].push(p);
        });
        const sortedKeys = Object.keys(groupedByMobile).map(Number).sort((a, b) => a - b);
        sortedKeys.forEach(k => {
          const list = groupedByMobile[k];
          const groupItems = list.map((photo, idx) => {
            let role = 'info_pages';
            if (idx === 0) role = 'cover_front';
            else if (idx === 1 && list.length > 2) role = 'cover_back';
            else if (idx === 1 && list.length === 2) role = 'info_pages';
            else role = 'info_pages';
            return { photo, role };
          });
          bookGroups.push(groupItems);
        });
      } else if (schemeVal === 'smart_ai' && unassigned.length >= 2) {
        // Вариант 2: Интеллектуальный ИИ-классификатор Gemini Vision (авто-поиск обложек, мульти-титулы, дефекты)
        if (statusText) statusText.textContent = '🤖 ИИ Gemini определяет границы книг, титулы, иллюстрации и дефекты...';
        try {
          if (!currentApiKey) await loadSavedKey();
          const reqPhotos = unassigned.map((p, idx) => ({
            data: p.data || p.preview || p.cameraOriginal,
            mime: p.mime || 'image/jpeg',
            name: p.name || `photo_${idx}`
          }));

          const res = await fetch('/api/ai_classify_batch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              api_key: currentApiKey,
              photos: reqPhotos
            })
          });
          const data = await res.json();
          if (data.success && Array.isArray(data.items) && data.items.length > 0) {
            const aiItems = data.items;
            const booksMap = {};
            aiItems.forEach(item => {
              const photo = unassigned[item.index];
              if (!photo) return;
              const bNum = item.book_num || 1;
              if (!booksMap[bNum]) booksMap[bNum] = [];
              booksMap[bNum].push({
                photo: photo,
                role: item.role || 'info_pages'
              });
            });
            const bKeys = Object.keys(booksMap).map(Number).sort((a, b) => a - b);
            bKeys.forEach(k => bookGroups.push(booksMap[k]));
          }
        } catch (e) {
          console.error('Ошибка ИИ классификатора:', e);
        }
      }

      // Fallback если ИИ не вернул группы или выбрана фиксированная схема по N фото
      if (bookGroups.length === 0) {
        const perBook = parseInt(schemeVal, 10) || 3;
        for (let i = 0; i < unassigned.length; i += perBook) {
          const slice = unassigned.slice(i, i + perBook);
          const groupItems = slice.map((photo, pIdx) => {
            let role = 'info_pages';
            if (pIdx === 0) role = 'cover_front';
            else if (pIdx === 1 && perBook > 2) role = 'cover_back';
            else if (pIdx === 1 && perBook === 2) role = 'info_pages';
            else if (pIdx === 2) role = 'info_pages';
            else if (pIdx === 3) role = 'illustrations';
            else if (pIdx >= 4) role = 'mantra_defects';
            return { photo, role };
          });
          bookGroups.push(groupItems);
        }
      }

      let createdCount = 0;

      bookGroups.forEach((group, chunkIdx) => {
        const bookArtNum = currentNum + chunkIdx;
        const bookArtStr = `DP-B-${String(bookArtNum).padStart(5, '0')}`;
        const bookBarcode = generateEan13FromArticle(bookArtStr);

        let targetBook = null;
        if (chunkIdx === 0 && booksSession.length > 0) {
          const first = booksSession[0];
          const hasAnyPhoto = Boolean(first.slots.cover_front || (first.slots.cover_back && (Array.isArray(first.slots.cover_back) ? first.slots.cover_back.length > 0 : true)) || (first.slots.info_pages && first.slots.info_pages.length > 0));
          if (!hasAnyPhoto) {
            targetBook = first;
            targetBook.article = bookArtStr;
            if (!targetBook.formData) targetBook.formData = {};
            targetBook.formData.article = bookArtStr;
            targetBook.formData.article_number = String(bookArtNum).padStart(5, '0');
            targetBook.formData.barcode = bookBarcode;
          }
        }

        if (!targetBook) {
          const nextId = booksSession.length > 0 ? Math.max(...booksSession.map(b => b.id)) + 1 : 1;
          targetBook = {
            id: nextId,
            article: bookArtStr,
            title: `Книга #${nextId}`,
            slots: {
              cover_front: null,
              cover_back: [],
              info_pages: [],
              illustrations: [],
              mantra_defects: []
            },
            formData: {
              article: bookArtStr,
              article_number: String(bookArtNum).padStart(5, '0'),
              barcode: bookBarcode,
              auto_package_adder: true
            }
          };
          booksSession.push(targetBook);
        }

        // Раскладываем фото группы по слотам
        group.forEach(({ photo, role }) => {
          let slot = role || 'info_pages';
          if (!['cover_front', 'cover_back', 'info_pages', 'illustrations', 'mantra_defects'].includes(slot)) {
            slot = 'info_pages';
          }

          photo.assignedBookId = targetBook.id;
          photo.assignedSlot = slot;

          if (['cover_back', 'info_pages', 'illustrations', 'mantra_defects'].includes(slot)) {
            if (!Array.isArray(targetBook.slots[slot])) {
              targetBook.slots[slot] = targetBook.slots[slot] ? [targetBook.slots[slot]] : [];
            }
            if (!targetBook.slots[slot].some(p => p.id === photo.id)) {
              targetBook.slots[slot].push(photo);
            }
          } else {
            // Одиночные слоты: если уже занят, отправляем в info_pages
            if (targetBook.slots[slot]) {
              slot = 'info_pages';
              photo.assignedSlot = slot;
              if (!targetBook.slots[slot].some(p => p.id === photo.id)) {
                targetBook.slots[slot].push(photo);
              }
            } else {
              targetBook.slots[slot] = photo;
            }
          }

          // Запускаем параллельное вырезание фона и авто-поворот
          queueAiBackgroundRemoval(photo.id);
        });

        // Запускаем фоновое распознавание книги Gemini
        queueBookAiRecognition(targetBook.id);
        createdCount++;
      });

      // Обновляем начальный артикул для следующей пачки
      const nextFutureArt = `DP-B-${String(currentNum + bookGroups.length).padStart(5, '0')}`;
      if (startArtInput) startArtInput.value = nextFutureArt;

      renderPool();
      renderBooksTabs();
      renderActiveBookSlots();
      scheduleAutoSave();

      if (statusText) {
        statusText.textContent = `⚡ Конвейер: ${unassigned.length} фото распределено по ${createdCount} книгам (${startArtVal} ... DP-B-${String(currentNum + bookGroups.length - 1).padStart(5, '0')}). Идет параллельная обработка и ИИ-анализ!`;
      }
      if (statusCounter) {
        statusCounter.textContent = `${createdCount} книг в работе`;
      }
      showToast(`🚀 Распределено ${unassigned.length} фото по ${createdCount} книгам! Запущен параллельный ИИ-анализ.`);
    }

    function updatePipelineStatus(msg) {
      const statusBox = document.getElementById('batchPipelineStatus');
      const statusText = document.getElementById('batchPipelineStatusText');
      if (statusBox && statusText) {
        statusBox.classList.remove('hidden');
        statusText.textContent = `⚡ ${msg}`;
      }
    }



// -------------------------------------------------------------
// QR-КОД, ТУННЕЛЬ И МОБИЛЬНЫЙ СЛУШАТЕЛЬ
// -------------------------------------------------------------
    // QR-КОД И ТУННЕЛЬ (CLOUDFLARE + ЛОКАЛЬНЫЙ WI-FI, ПОРТ 8095)
    // -------------------------------------------------------------
    let tunnelPollTimer = null;
    let cachedTunnelUrl = '';
    let cachedLocalUrl = '';
    let cachedLocalIp = '';
    let isVpnActiveOnMac = false;
    let hasUserSelectedTab = false;
    let activeQrTab = 'wifi'; // По умолчанию Wi-Fi: локально, мгновенно, без блокировок операторов!
    let currentRenderedQrUrl = '';

    async function loadMobileUrl() {
      try {
        const res = await fetch('/api/get_tunnel_url');
        const data = await res.json();
        if (data.url) cachedTunnelUrl = data.url + '/mobile';
        if (data.local_url) cachedLocalUrl = data.local_url + '/mobile';
        if (data.local_ip) cachedLocalIp = data.local_ip;
        if (data.has_vpn) {
          isVpnActiveOnMac = true;
        }

        const qrModalEl = document.getElementById('qrModal');
        if (qrModalEl && !qrModalEl.classList.contains('hidden')) {
          updateQrModalView();
        }

        if (cachedTunnelUrl) {
          if (tunnelPollTimer) { clearInterval(tunnelPollTimer); tunnelPollTimer = null; }
        } else {
          if (!tunnelPollTimer) tunnelPollTimer = setInterval(loadMobileUrl, 1500);
        }
      } catch (e) {
        if (!tunnelPollTimer) tunnelPollTimer = setInterval(loadMobileUrl, 2000);
      }
    }

    function switchQrTab(tab, isManual = true) {
      if (isManual) hasUserSelectedTab = true;
      activeQrTab = tab;
      const btnCloudflare = document.getElementById('tabCloudflare');
      const btnWifi = document.getElementById('tabWifi');
      if (tab === 'cloudflare') {
        if (btnCloudflare) btnCloudflare.className = 'flex-1 py-1.5 px-2 rounded-lg font-bold transition bg-amber-500 text-slate-950 shadow';
        if (btnWifi) btnWifi.className = 'flex-1 py-1.5 px-2 rounded-lg font-medium transition text-slate-400 hover:text-white';
      } else {
        if (btnWifi) btnWifi.className = 'flex-1 py-1.5 px-2 rounded-lg font-bold transition bg-amber-500 text-slate-950 shadow';
        if (btnCloudflare) btnCloudflare.className = 'flex-1 py-1.5 px-2 rounded-lg font-medium transition text-slate-400 hover:text-white';
      }
      currentRenderedQrUrl = '';
      updateQrModalView();
    }

    function updateQrModalView() {
      const isCloudflare = activeQrTab === 'cloudflare';
      const label = document.getElementById('qrUrlLabel');
      const desc = document.getElementById('qrModeDesc');
      const helpTitle = document.getElementById('qrHelpTitle');
      const helpLine1 = document.getElementById('qrHelpLine1');
      const helpLine2 = document.getElementById('qrHelpLine2');
      const vpnBadge = document.getElementById('qrVpnBadge');

      if (vpnBadge) {
        if (isCloudflare) {
          vpnBadge.innerHTML = '🌐 <b>Режим Cloudflare:</b> если мобильный оператор блокирует ссылку — переключитесь на <b>«📶 Wi-Fi сеть»</b>!';
        } else {
          vpnBadge.innerHTML = '📶 <b>Локальный Wi-Fi:</b> телефон и Mac должны быть в одной сети Wi-Fi!';
        }
      }

      if (isCloudflare) {
        if (label) label.textContent = 'Прямой интернет-адрес (Cloudflare):';
        if (desc) desc.textContent = 'Наведите камеру смартфона (с VPN или без):';
        if (helpTitle) helpTitle.textContent = '🛡️ Cloudflare Quick Tunnel (порт 8095):';
        if (helpLine1) helpLine1.textContent = '• ✅ Идеально для работы с VPN на телефоне или компьютере!';
        if (helpLine2) helpLine2.textContent = '• Работает через любую сеть со сквозным шифрованием HTTPS.';

        if (cachedTunnelUrl) {
          currentMobileUrl = cachedTunnelUrl;
          renderQrCode(cachedTunnelUrl, false);
        } else {
          const fallbackUrl = cachedLocalUrl || 'http://127.0.0.1:8095/mobile';
          currentMobileUrl = fallbackUrl;
          renderQrCode(fallbackUrl, true);
        }
      } else {
        if (label) label.textContent = 'Локальный Wi-Fi адрес:';
        if (desc) desc.textContent = 'Смартфон и компьютер в одной Wi-Fi сети:';
        if (helpTitle) helpTitle.textContent = '📶 Локальное прямое Wi-Fi подключение:';
        if (helpLine1) helpLine1.textContent = `• IP вашего компьютера в сети: ${cachedLocalIp || 'Wi-Fi'}`;
        if (helpLine2) helpLine2.textContent = '• ⚠️ Если на телефоне или Mac включен VPN — переключитесь на вкладку «🌐 Cloudflare» выше!';

        const wifiUrl = cachedLocalUrl || 'http://127.0.0.1:8095/mobile';
        currentMobileUrl = wifiUrl;
        renderQrCode(wifiUrl, false);
      }
    }

    function renderQrCode(url, isWarmingUp = false) {
      if (currentRenderedQrUrl === url && document.getElementById('qrcodeCanvas')?.hasChildNodes()) {
        return; // НЕ перерисовываем и не мерцаем, если этот URL уже отображен!
      }
      currentRenderedQrUrl = url;

      const container = document.getElementById('qrcodeCanvas');
      if (!container) return;
      container.innerHTML = '';
      try {
        if (typeof QRCode !== 'undefined') {
          new QRCode(container, {
            text: url,
            width: 190,
            height: 190,
            colorDark: "#0f172a",
            colorLight: "#ffffff",
            correctLevel: QRCode.CorrectLevel.M
          });
          setTimeout(() => {
            const cvs = container.querySelector('canvas');
            const img = container.querySelector('img');
            if (cvs && (!img || !img.src || img.src.length < 50)) {
              cvs.style.display = 'block';
            }
          }, 40);
        } else {
          container.innerHTML = `<img src="https://api.qrserver.com/v1/create-qr-code/?size=190x190&data=${encodeURIComponent(url)}" alt="QR Code" class="w-[190px] h-[190px] mx-auto rounded-lg">`;
        }
      } catch (err) {
        container.innerHTML = `<img src="https://api.qrserver.com/v1/create-qr-code/?size=190x190&data=${encodeURIComponent(url)}" alt="QR Code" class="w-[190px] h-[190px] mx-auto rounded-lg">`;
      }

      const urlText = document.getElementById('mobileUrlText');
      if (!urlText) return;
      if (isWarmingUp) {
        urlText.innerHTML = `
          <div class="text-amber-400 font-semibold mb-1">⏳ Подключение глобального Cloudflare-туннеля...</div>
          <div class="text-[11px] text-slate-400 mb-2">Генерация публичного HTTPS-адреса... Вы можете переключиться на вкладку <button type="button" onclick="switchQrTab('wifi')" class="text-amber-400 underline font-bold">«📶 Wi-Fi сеть»</button> для мгновенной работы.</div>
          <a href="${url}" target="_blank" class="text-slate-400 underline break-all text-[11px]">${url}</a>
        `;
      } else {
        urlText.innerHTML = `
          <a href="${url}" target="_blank" class="text-amber-400 hover:text-amber-300 underline break-all font-semibold block mb-1">${url}</a>
          <button type="button" onclick="copyMobileUrl()" id="copyUrlBtn" class="text-[10px] px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700">📋 Скопировать ссылку</button>
        `;
      }
    }

    function copyMobileUrl() {
      if (currentMobileUrl) {
        navigator.clipboard.writeText(currentMobileUrl).then(() => {
          const btn = document.getElementById('copyUrlBtn');
          if (btn) btn.textContent = '✅ Скопировано!';
          setTimeout(() => { if (btn) btn.textContent = '📋 Скопировать ссылку'; }, 2000);
        });
      }
    }

    function openQrModal() {
      const modal = document.getElementById('qrModal');
      if (modal) {
        modal.classList.remove('hidden');
      }
      currentRenderedQrUrl = ''; // Сброс для гарантированной перерисовки при открытии
      updateQrModalView(); // Мгновенная отрисовка из кэша без задержек
      loadMobileUrl(); // Фоновое обновление
    }
    function closeQrModal() {
      const modal = document.getElementById('qrModal');
      if (modal) modal.classList.add('hidden');
    }

    window.openQrModal = openQrModal;
    window.closeQrModal = closeQrModal;
    window.switchQrTab = switchQrTab;
    window.restartTunnelManual = restartTunnelManual;
    window.copyMobileUrl = copyMobileUrl;

    async function restartTunnelManual() {
      const btn = document.getElementById('btnRestartTunnel');
      const text = document.getElementById('btnRestartTunnelText');
      if (btn) btn.disabled = true;
      if (text) text.textContent = '⏳ Перезапуск туннеля и поиск сети...';

      try {
        const res = await fetch('/api/restart_tunnel');
        const data = await res.json();
        if (data.url) cachedTunnelUrl = data.url + '/mobile';
        if (data.local_url) cachedLocalUrl = data.local_url + '/mobile';
        if (data.local_ip) cachedLocalIp = data.local_ip;
        updateQrModalView();
        if (text) text.textContent = '✅ Туннель обновлен!';
        setTimeout(() => {
          if (text) text.textContent = 'Сменился Wi-Fi? Переподключить туннель';
          if (btn) btn.disabled = false;
        }, 2500);
      } catch (e) {
        if (text) text.textContent = '⚠️ Ошибка перезапуска';
        setTimeout(() => {
          if (text) text.textContent = 'Сменился Wi-Fi? Переподключить туннель';
          if (btn) btn.disabled = false;
        }, 2500);
      }
    }

    // Слушатель поступления фото со смартфона
    function startMobileEventListener() {
      setInterval(async () => {
        try {
          const res = await fetch('/api/check_mobile_event?last_id=' + lastMobileEventId);
          const data = await res.json();
          if (data.has_new && data.event_id > lastMobileEventId) {
            lastMobileEventId = data.event_id;
            if (data.images && data.images.length > 0) {
              const addedPhotos = [];
              data.images.forEach(img => {
                const prev = 'data:image/jpeg;base64,' + img.data;
                const photoObj = {
                  id: 'photo_' + Math.random().toString(36).substr(2, 9),
                  name: img.name || 'mobile_photo.jpg',
                  mime: img.mime || 'image/jpeg',
                  data: img.data,
                  bookIndex: img.book_index || null,
                  preview: prev,
                  cameraOriginal: prev,
                  rawOriginal: prev,
                  croppedBase: null,
                  isCropped: false,
                  isAiProcessed: false,
                  assignedBookId: null,
                  assignedSlot: null
                };
                photoPool.push(photoObj);
                addedPhotos.push(photoObj);
              });
              renderPool();
              scheduleAutoSave();
              closeQrModal();
              playNotificationSound();
              showToast(`📱 Со смартфона получено ${data.images.length} фото!`);
              // П. 3.2 спецификации: вырезание фона стола запускается только для обложек после их назначения в слоты
              if (document.getElementById('batchAutoDistributeToggle')?.checked) {
                setTimeout(() => {
                  runBatchDistributePipeline(true);
                }, 350);
              }
            }
          }
        } catch (e) {}
      }, 1500);
    }

    function playNotificationSound() {
      try {
        const ctx = new (window.AudioContext || window.webkitAudioContext)();
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.frequency.setValueAtTime(587.33, ctx.currentTime);
        osc.frequency.setValueAtTime(880.00, ctx.currentTime + 0.1);
        gain.gain.setValueAtTime(0.15, ctx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.3);
        osc.start(ctx.currentTime);
        osc.stop(ctx.currentTime + 0.3);
      } catch (e) {}
    }

    // Экспорт в глобальное пространство window
    window.deletePhotoFromPool = deletePhotoFromPool;
    window.deleteSelectedPhotoFromPool = deleteSelectedPhotoFromPool;
    window.clearPool = clearPool;

