/**
 * studio.js: Фотостудия, Cropper.js, 360° поворот, фильтры и история версий.
 */

    // -------------------------------------------------------------
    // PHOTO STUDIO & CROPPER.JS ОБРАБОТКА ФОТО
    // -------------------------------------------------------------
    var currentEditingPhoto = null;
    var cropperInstance = null;
    var isStudioOpen = false;
    var hasUnsavedStudioChanges = false;
    let studioCurrentRotation = 0;
    let studioBaseCardinal = 0;
    let studioBaseRotation = 0;
    let studioFineRotation = 0;
    let cropRatio = 'none';
    let isFreeCroppingActive = false;
    let studioLoadedSourceType = 'full'; // 'full' | 'cropped'
    let preCropImageSrc = null;
    let hasUnsavedCrop = false;
    let studioCropBoxOnOriginal = null;
    let isProgrammaticCropBoxUpdate = false;
    let studioState = {
      whiten: 0,
      brightness: 0,
      contrast: 0,
      saturation: 0
    };

    function markStudioChanged(label = 'Изменение', immediate = false) {
      hasUnsavedStudioChanges = true;
      updateAiBatchBtnState();
    }

    function updateAiBatchBtnState() {
      const btn = document.getElementById('aiBatchBtn');
      const btnText = document.getElementById('aiBatchBtnText');
      if (!btn) return;
      const curBook = typeof window.getActiveBook === 'function' ? window.getActiveBook() : null;
      const isCurBusy = Boolean(curBook && curBook.isAiRecognizing);
      if (isCurBusy) {
        btn.disabled = true;
        btn.classList.add('opacity-50', 'cursor-not-allowed', 'grayscale');
        btn.title = 'Идет распознавание этой книги через Gemini...';
        if (btnText) {
          btnText.textContent = '⏳ Анализ книги через Gemini...';
        }
      } else {
        btn.disabled = false;
        btn.classList.remove('opacity-50', 'cursor-not-allowed', 'grayscale');
        btn.title = 'Распознать автора, название, год и выходные данные книги через Gemini Vision';
        if (btnText && btnText.textContent !== '✓ Успешно распознано!') {
          btnText.textContent = 'Распознать эту книгу через Gemini 3.5';
        }
      }
    }
    window.updateAiBatchBtnState = updateAiBatchBtnState;

    // -------------------------------------------------------------
    // БЕЗОПАСНЫЙ URL ИСТОЧНИКА ДЛЯ СТУДИИ (ПРОКСИРОВАНИЕ S3/CORS И КИРИЛЛИЦА)
    // -------------------------------------------------------------
    function getSafeStudioSourceUrl(url) {
      if (!url || typeof url !== 'string') return url;
      url = url.trim();
      if (url.startsWith('data:') || url.startsWith('blob:')) {
        return url;
      }
      if (url.startsWith('/')) {
        try {
          return encodeURI(decodeURI(url));
        } catch (e) {
          return url;
        }
      }
      if (url.startsWith('http://') || url.startsWith('https://')) {
        try {
          const parsed = new URL(url);
          if (typeof window !== 'undefined' && parsed.host === window.location.host) {
            return parsed.pathname + parsed.search;
          }
          return `/api/image_proxy?url=${encodeURIComponent(url)}`;
        } catch (e) {
          return `/api/image_proxy?url=${encodeURIComponent(url)}`;
        }
      }
      return url;
    }
    window.getSafeStudioSourceUrl = getSafeStudioSourceUrl;

    // -------------------------------------------------------------
    // ИСТОРИЯ ИЗМЕНЕНИЙ ФОТО (UNDO / ИСТОРИЯ ВЕРСИЙ)
    // -------------------------------------------------------------
    function initPhotoHistory(photo) {
      if (!photo) return;
      if (!Array.isArray(photo.history) || photo.history.length === 0) {
        photo.history = [];
        const baseSrc = photo.cameraOriginal || photo.rawOriginal || photo.preview;
        photo.history.push({
          label: 'Снимок с камеры',
          timestamp: Date.now(),
          preview: photo.preview || baseSrc,
          data: photo.data,
          croppedBase: photo.croppedBase || null,
          rawOriginal: photo.rawOriginal || baseSrc,
          cameraOriginal: photo.cameraOriginal || baseSrc,
          aiWhiteOriginal: photo.aiWhiteOriginal || null,
          isCropped: Boolean(photo.isCropped),
          isAiProcessed: Boolean(photo.isAiProcessed),
          inCropMode: false,
          hasCropBox: Boolean(photo.isCropped),
          cropBoxOnOriginal: photo.cropBoxOnOriginal ? { ...photo.cropBoxOnOriginal } : null,
          cropRelative: photo.cropRelative ? { ...photo.cropRelative } : (photo.aiCropRelative ? { ...photo.aiCropRelative } : null),
          cropRatio: 'none',
          whiten: Number(photo.whiten) || 0,
          brightness: Number(photo.brightness) || 0,
          contrast: Number(photo.contrast) || 0,
          saturation: Number(photo.saturation) || 0,
          rotation: Number(photo.rotation) || 0,
          cardinal: Math.round(((photo.rotation || 0) % 360) / 90) * 90 % 360
        });
        photo.historyIndex = 0;
      }
      if (typeof photo.historyIndex !== 'number' || photo.historyIndex < 0) {
        photo.historyIndex = photo.history.length - 1;
      }
    }

    function renderCroppedFromFullSourceAsync(src, rotationDeg = 0, rel = null) {
      return new Promise((resolve, reject) => {
        if (!src) return reject(new Error('Нет источника для рендеринга'));
        const safeSrc = getSafeStudioSourceUrl(src);
        const img = new Image();
        if (safeSrc.startsWith('http://') || safeSrc.startsWith('https://') || safeSrc.startsWith('/api/image_proxy')) {
          img.crossOrigin = 'anonymous';
        }
        img.onload = () => {
          try {
            const nw = img.naturalWidth || img.width;
            const nh = img.naturalHeight || img.height;
            const deg = ((Number(rotationDeg) || 0) % 360 + 360) % 360;
            const rad = (deg * Math.PI) / 180;
            const absCos = Math.abs(Math.cos(rad));
            const absSin = Math.abs(Math.sin(rad));

            const rotW = Math.max(1, Math.round(nw * absCos + nh * absSin));
            const rotH = Math.max(1, Math.round(nw * absSin + nh * absCos));

            // 1. Отрисовываем повернутый полный кадр на чистом белом фоне (#FFFFFF)
            const rotCanvas = document.createElement('canvas');
            rotCanvas.width = rotW;
            rotCanvas.height = rotH;
            const rCtx = rotCanvas.getContext('2d');
            rCtx.fillStyle = '#ffffff';
            rCtx.fillRect(0, 0, rotW, rotH);
            rCtx.translate(rotW / 2, rotH / 2);
            rCtx.rotate(rad);
            rCtx.drawImage(img, -nw / 2, -nh / 2);

            // 2. Если переданы относительные координаты рамки — вырезаем точную область
            if (rel && rel.w > 0.01 && rel.h > 0.01) {
              const rx = Math.max(0, Math.min(0.98, Number(rel.x) || 0));
              const ry = Math.max(0, Math.min(0.98, Number(rel.y) || 0));
              const rw = Math.max(0.02, Math.min(1 - rx, Number(rel.w) || 1));
              const rh = Math.max(0.02, Math.min(1 - ry, Number(rel.h) || 1));

              const sx = Math.round(rx * rotW);
              const sy = Math.round(ry * rotH);
              const sw = Math.max(1, Math.round(rw * rotW));
              const sh = Math.max(1, Math.round(rh * rotH));

              const outCanvas = document.createElement('canvas');
              outCanvas.width = sw;
              outCanvas.height = sh;
              const oCtx = outCanvas.getContext('2d');
              oCtx.fillStyle = '#ffffff';
              oCtx.fillRect(0, 0, sw, sh);
              oCtx.drawImage(rotCanvas, sx, sy, sw, sh, 0, 0, sw, sh);
              resolve(outCanvas.toDataURL('image/jpeg', 0.94));
              return;
            }

            resolve(rotCanvas.toDataURL('image/jpeg', 0.94));
          } catch (err) {
            reject(err);
          }
        };
        img.onerror = () => reject(new Error('Не удалось загрузить изображение'));
        img.src = safeSrc;
      });
    }
    window.renderCroppedFromFullSourceAsync = renderCroppedFromFullSourceAsync;

    function cropImageSourceAsync(src, rel) {
      return renderCroppedFromFullSourceAsync(src, 0, rel);
    }
    window.cropImageSourceAsync = cropImageSourceAsync;

    function transformCropRelativeBy90(rel, direction) {
      if (!rel || !rel.w || !rel.h) return null;
      const rx = Number(rel.x) || 0;
      const ry = Number(rel.y) || 0;
      const rw = Number(rel.w) || 1;
      const rh = Number(rel.h) || 1;
      if (direction > 0) {
        // +90° по часовой стрелке
        return {
          x: Math.max(0, Math.min(0.98, 1 - ry - rh)),
          y: Math.max(0, Math.min(0.98, rx)),
          w: Math.max(0.02, Math.min(1, rh)),
          h: Math.max(0.02, Math.min(1, rw))
        };
      }
      // -90° против часовой стрелки
      return {
        x: Math.max(0, Math.min(0.98, ry)),
        y: Math.max(0, Math.min(0.98, 1 - rx - rw)),
        w: Math.max(0.02, Math.min(1, rh)),
        h: Math.max(0.02, Math.min(1, rw))
      };
    }

    function cropRelativesEqual(r1, r2) {
      if (!r1 && !r2) return true;
      if (!r1 || !r2) return false;
      return Math.abs((r1.x || 0) - (r2.x || 0)) < 0.0015 &&
             Math.abs((r1.y || 0) - (r2.y || 0)) < 0.0015 &&
             Math.abs((r1.w || 0) - (r2.w || 0)) < 0.0015 &&
             Math.abs((r1.h || 0) - (r2.h || 0)) < 0.0015;
    }

    function updateRotaryDialUI(deg) {
      const normalized = Math.round((((deg % 360) + 360) % 360) * 10) / 10;
      const rotor = document.getElementById('rotaryDialRotor');
      if (rotor) {
        rotor.style.transform = `rotate(${normalized}deg)`;
      }
      const centerDisplay = document.getElementById('rotaryCenterDisplay');
      if (centerDisplay) {
        centerDisplay.style.transform = `rotate(-${normalized}deg)`;
      }
      const angleText = document.getElementById('rotaryAngleText');
      if (angleText) {
        const displayAngle = normalized > 180
          ? (normalized - 360).toFixed(1)
          : normalized.toFixed(1);
        const sign = parseFloat(displayAngle) > 0 ? '+' : '';
        angleText.textContent = `${sign}${displayAngle}°`;
      }
    }

    function applyFiltersToImageAsync(src, filters) {
      return new Promise((resolve) => {
        if (!src) return resolve(src);
        const W = filters ? (Number(filters.whiten) || 0) : 0;
        const B = filters ? (Number(filters.brightness) || 0) : 0;
        const C = filters ? (Number(filters.contrast) || 0) : 0;
        const S = filters ? (Number(filters.saturation) || 0) : 0;
        if (W === 0 && B === 0 && C === 0 && S === 0) {
          return resolve(src);
        }
        const safeSrc = getSafeStudioSourceUrl(src);
        const img = new Image();
        if (safeSrc.startsWith('http://') || safeSrc.startsWith('https://') || safeSrc.startsWith('/api/image_proxy')) {
          img.crossOrigin = 'anonymous';
        }
        img.onload = () => {
          try {
            const canvas = document.createElement('canvas');
            canvas.width = img.naturalWidth || img.width;
            canvas.height = img.naturalHeight || img.height;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(img, 0, 0);
            applyPixelFiltersToCanvas(canvas, { whiten: W, brightness: B, contrast: C, saturation: S });
            resolve(canvas.toDataURL('image/jpeg', 0.92));
          } catch (e) {
            resolve(src);
          }
        };
        img.onerror = () => resolve(src);
        img.src = safeSrc;
      });
    }
    window.applyFiltersToImageAsync = applyFiltersToImageAsync;

    function updateCurrentPhotoPreviewFromStudio(callback) {
      if (!currentEditingPhoto) {
        if (typeof callback === 'function') callback();
        return;
      }

      const photo = currentEditingPhoto;
      photo.whiten = studioState.whiten;
      photo.brightness = studioState.brightness;
      photo.contrast = studioState.contrast;
      photo.saturation = studioState.saturation;
      photo.rotation = studioCurrentRotation;
      photo.isProcessed = Boolean(
        photo.isCropped ||
        studioState.whiten > 0 ||
        studioState.brightness !== 0 ||
        studioState.contrast !== 0 ||
        studioState.saturation !== 0 ||
        studioCurrentRotation !== 0 ||
        photo.isAiProcessed
      );

      const getBasePromise = () => {
        if (photo.isCropped && photo.croppedBase) {
          return Promise.resolve(photo.croppedBase);
        }
        const fullSource = getPhotoFullSource(photo);
        if (!fullSource) return Promise.resolve(null);
        if (Math.abs(studioCurrentRotation) > 0.05) {
          return renderCroppedFromFullSourceAsync(fullSource, studioCurrentRotation, null);
        }
        return Promise.resolve(fullSource);
      };

      getBasePromise().then(base => {
        if (!base) {
          if (typeof callback === 'function') callback();
          return;
        }
        return applyFiltersToImageAsync(base, studioState).then(filteredUrl => {
          if (!photo) return;
          photo.preview = filteredUrl;
          photo.data = filteredUrl.includes(',') ? filteredUrl.split(',')[1] : filteredUrl;
          renderPool();
          renderActiveBookSlots();
          scheduleAutoSave();
          if (typeof callback === 'function') callback();
        });
      }).catch(() => {
        if (typeof callback === 'function') callback();
      });
    }

    let isUndoingAction = false;

    function getStudioCurrentState(label = 'Изменение') {
      if (!currentEditingPhoto) return null;
      return {
        label: label,
        timestamp: Date.now(),
        preview: currentEditingPhoto.preview,
        data: currentEditingPhoto.data,
        croppedBase: currentEditingPhoto.croppedBase,
        rawOriginal: currentEditingPhoto.rawOriginal,
        cameraOriginal: currentEditingPhoto.cameraOriginal,
        aiWhiteOriginal: currentEditingPhoto.aiWhiteOriginal,
        isCropped: Boolean(currentEditingPhoto.isCropped),
        isAiProcessed: Boolean(currentEditingPhoto.isAiProcessed),
        inCropMode: Boolean(isFreeCroppingActive),
        hasCropBox: Boolean(cropperInstance && cropperInstance.cropped),
        cropBoxOnOriginal: studioCropBoxOnOriginal ? { ...studioCropBoxOnOriginal } : (currentEditingPhoto.cropBoxOnOriginal ? { ...currentEditingPhoto.cropBoxOnOriginal } : null),
        cropRelative: currentEditingPhoto.cropRelative ? { ...currentEditingPhoto.cropRelative } : (currentEditingPhoto.aiCropRelative ? { ...currentEditingPhoto.aiCropRelative } : null),
        cropRatio: cropRatio || 'none',
        whiten: Number(studioState.whiten) || 0,
        brightness: Number(studioState.brightness) || 0,
        contrast: Number(studioState.contrast) || 0,
        saturation: Number(studioState.saturation) || 0,
        rotation: Number(studioCurrentRotation) || 0,
        cardinal: Number(studioBaseCardinal) || 0
      };
    }

    function isStateIdentical(s1, s2) {
      if (!s1 || !s2) return false;
      return s1.whiten === s2.whiten &&
             s1.brightness === s2.brightness &&
             s1.contrast === s2.contrast &&
             s1.saturation === s2.saturation &&
             Math.abs((s1.rotation || 0) - (s2.rotation || 0)) < 0.1 &&
             s1.isCropped === s2.isCropped &&
             s1.isAiProcessed === s2.isAiProcessed &&
             Boolean(s1.inCropMode) === Boolean(s2.inCropMode) &&
             s1.croppedBase === s2.croppedBase &&
             s1.aiWhiteOriginal === s2.aiWhiteOriginal &&
             s1.cropRatio === s2.cropRatio &&
             cropRelativesEqual(s1.cropRelative, s2.cropRelative);
    }

    function recordStudioStep(label = 'Изменение') {
      if (!currentEditingPhoto || isUndoingAction) return;
      initPhotoHistory(currentEditingPhoto);

      // Если оператор сделал действие после серии отмен, отрезаем ветку redo
      if (currentEditingPhoto.historyIndex < currentEditingPhoto.history.length - 1) {
        currentEditingPhoto.history = currentEditingPhoto.history.slice(0, currentEditingPhoto.historyIndex + 1);
      }

      const newState = getStudioCurrentState(label);
      if (!newState) return;

      const lastState = currentEditingPhoto.history[currentEditingPhoto.historyIndex];
      if (lastState && isStateIdentical(lastState, newState)) {
        return;
      }

      // Если мы фиксируем обрезку (inCropMode: false) с теми же координатами рамки,
      // что и на последнем шаге правки рамки (inCropMode: true) — обновляем этот шаг на месте,
      // чтобы «Шаг назад» откатывал сразу в 1 клик, а не в 2!
      if (lastState && lastState.inCropMode && !newState.inCropMode &&
          cropRelativesEqual(lastState.cropRelative, newState.cropRelative) &&
          Math.abs((lastState.rotation || 0) - (newState.rotation || 0)) < 0.1 &&
          lastState.aiWhiteOriginal === newState.aiWhiteOriginal) {
        currentEditingPhoto.history[currentEditingPhoto.historyIndex] = newState;
        updateStudioHistoryUI();
        markStudioChanged(label, false);
        return;
      }

      currentEditingPhoto.history.push(newState);
      if (currentEditingPhoto.history.length > 40) {
        currentEditingPhoto.history.shift();
      }
      currentEditingPhoto.historyIndex = currentEditingPhoto.history.length - 1;

      updateStudioHistoryUI();
      markStudioChanged(label, false);
    }

    const pushPhotoHistory = (photo, label) => recordStudioStep(label);

    function commitStudioSliderStep(label) {
      updateCurrentPhotoPreviewFromStudio(() => {
        recordStudioStep(label);
      });
    }

    function applyStudioState(targetState, callback) {
      if (!currentEditingPhoto || !targetState) return;

      const wasInCropMode = Boolean(isFreeCroppingActive);
      const prevAiWhite = currentEditingPhoto.aiWhiteOriginal || null;

      // 1. Обновляем параметры студии
      studioState.whiten = targetState.whiten || 0;
      studioState.brightness = targetState.brightness || 0;
      studioState.contrast = targetState.contrast || 0;
      studioState.saturation = targetState.saturation || 0;
      studioCurrentRotation = Number(targetState.rotation) || 0;
      studioBaseCardinal = Number(targetState.cardinal) || (Math.round(studioCurrentRotation / 90) * 90 % 360);
      studioBaseRotation = studioCurrentRotation;
      studioFineRotation = 0;
      cropRatio = targetState.cropRatio || 'none';
      studioCropBoxOnOriginal = targetState.cropBoxOnOriginal ? { ...targetState.cropBoxOnOriginal } : null;

      // 2. Обновляем контролы UI
      const slW = document.getElementById('sliderWhiten'); if (slW) slW.value = studioState.whiten;
      const slB = document.getElementById('sliderBrightness'); if (slB) slB.value = studioState.brightness;
      const slC = document.getElementById('sliderContrast'); if (slC) slC.value = studioState.contrast;
      const slS = document.getElementById('sliderSaturation'); if (slS) slS.value = studioState.saturation;
      updateRotaryDialUI(studioCurrentRotation);
      updateStudioBadges();
      updateCropRatioButtons(cropRatio === 'none' ? null : cropRatio);

      // 3. Обновляем поля объекта photo
      currentEditingPhoto.preview = targetState.preview;
      currentEditingPhoto.data = targetState.data;
      currentEditingPhoto.croppedBase = targetState.croppedBase || null;
      currentEditingPhoto.isCropped = Boolean(targetState.isCropped);
      currentEditingPhoto.cropBoxOnOriginal = targetState.cropBoxOnOriginal ? { ...targetState.cropBoxOnOriginal } : null;
      currentEditingPhoto.cropRelative = targetState.cropRelative ? { ...targetState.cropRelative } : null;
      currentEditingPhoto.aiCropRelative = currentEditingPhoto.cropRelative;
      currentEditingPhoto.isAiProcessed = Boolean(targetState.isAiProcessed);
      currentEditingPhoto.whiten = studioState.whiten;
      currentEditingPhoto.brightness = studioState.brightness;
      currentEditingPhoto.contrast = studioState.contrast;
      currentEditingPhoto.saturation = studioState.saturation;
      currentEditingPhoto.rotation = studioCurrentRotation;
      if (targetState.aiWhiteOriginal !== undefined) {
        currentEditingPhoto.aiWhiteOriginal = targetState.aiWhiteOriginal;
      }
      currentEditingPhoto.isProcessed = Boolean(
        currentEditingPhoto.isCropped ||
        studioState.whiten > 0 ||
        studioState.brightness !== 0 ||
        studioState.contrast !== 0 ||
        studioState.saturation !== 0 ||
        studioCurrentRotation !== 0 ||
        currentEditingPhoto.isAiProcessed
      );

      const finishApply = () => {
        applyStudioFilterPreview();
        updateCropResetButtonVisibility();
        updateCropResolution();
        updateZoomBadge();
        renderPool();
        renderActiveBookSlots();
        scheduleAutoSave();
        if (typeof callback === 'function') callback();
      };

      const fullSource = getPhotoFullSource(currentEditingPhoto);
      const aiSourceChanged = (currentEditingPhoto.aiWhiteOriginal || null) !== prevAiWhite;

      // 4A. Если пользователь сейчас ВНУТРИ «Среза» и шаг относится к правке рамки (или есть рамка на том же исходнике) —
      // оставляем пользователя в «Срезе» и плавно возвращаем прошлую позицию рамки!
      const stayInCropMode = Boolean(targetState.inCropMode) || (wasInCropMode && Boolean(targetState.cropRelative) && !aiSourceChanged);
      if (stayInCropMode) {
        const applyFrameInCropMode = () => {
          isFreeCroppingActive = true;
          cropperInstance.rotateTo(studioCurrentRotation);
          fitStudioImageToContainer(false);
          applyCropAspectRatioToInstance(cropRatio);
          restoreCropFrameOnFullSource(true);
          updateStudioModeUI('crop');
          cropperInstance.setDragMode('move');
          finishApply();
        };

        if (studioLoadedSourceType !== 'full' || aiSourceChanged || !cropperInstance) {
          reloadStudioCropper(fullSource, applyFrameInCropMode, 'full');
        } else {
          applyFrameInCropMode();
        }
        return;
      }

      // 4B. Обычный режим (вне «Среза»): показываем чистый обрезанный результат (если обрезано) или чистый исходник
      const wantCroppedView = Boolean(currentEditingPhoto.isCropped && currentEditingPhoto.croppedBase);
      const targetSrc = wantCroppedView ? currentEditingPhoto.croppedBase : fullSource;
      const targetType = wantCroppedView ? 'cropped' : 'full';
      const currentImgSrc = (cropperInstance && cropperInstance.image) ? (cropperInstance.image.src || '') : '';
      const needReload = !cropperInstance || studioLoadedSourceType !== targetType || aiSourceChanged || (targetType === 'cropped' && currentImgSrc !== targetSrc);

      if (needReload) {
        reloadStudioCropper(targetSrc, () => {
          isFreeCroppingActive = false;
          if (targetType === 'full' && studioCurrentRotation !== 0) {
            cropperInstance.rotateTo(studioCurrentRotation);
          }
          fitStudioImageToContainer(false);
          cropperInstance.clear();
          cropperInstance.setDragMode('move');
          updateStudioModeUI('move');
          finishApply();
        }, targetType);
      } else {
        isFreeCroppingActive = false;
        if (targetType === 'full') {
          cropperInstance.rotateTo(studioCurrentRotation);
        }
        fitStudioImageToContainer(false);
        if (cropperInstance.cropped) cropperInstance.clear();
        cropperInstance.setDragMode('move');
        updateStudioModeUI('move');
        finishApply();
      }
    }

    function undoStudioAction() {
      if (!currentEditingPhoto) return;
      initPhotoHistory(currentEditingPhoto);

      if (currentEditingPhoto.historyIndex <= 0) {
        showToast('ℹ️ Это исходное состояние фото (история пуста)');
        return;
      }

      isUndoingAction = true;
      currentEditingPhoto.historyIndex--;
      const targetState = currentEditingPhoto.history[currentEditingPhoto.historyIndex];

      applyStudioState(targetState, () => {
        isUndoingAction = false;
        updateStudioHistoryUI();
        showToast(`↩️ Шаг назад: «${targetState.label}» (${currentEditingPhoto.historyIndex + 1}/${currentEditingPhoto.history.length})`);
      });
    }

    function redoStudioAction() {
      if (!currentEditingPhoto) return;
      initPhotoHistory(currentEditingPhoto);

      if (currentEditingPhoto.historyIndex >= currentEditingPhoto.history.length - 1) {
        showToast('ℹ️ Это самое последнее состояние');
        return;
      }

      isUndoingAction = true;
      currentEditingPhoto.historyIndex++;
      const targetState = currentEditingPhoto.history[currentEditingPhoto.historyIndex];

      applyStudioState(targetState, () => {
        isUndoingAction = false;
        updateStudioHistoryUI();
        showToast(`↪️ Шаг вперед: «${targetState.label}» (${currentEditingPhoto.historyIndex + 1}/${currentEditingPhoto.history.length})`);
      });
    }

    function updateStudioHistoryUI() {
      const btnUndo = document.getElementById('btnStudioUndo');
      const btnRedo = document.getElementById('btnStudioRedo');
      const btnSideUndo = document.getElementById('btnStudioSideUndo');
      const btnSideRedo = document.getElementById('btnStudioSideRedo');
      const histCounter = document.getElementById('studioHistoryCounter');

      if (!currentEditingPhoto) return;
      initPhotoHistory(currentEditingPhoto);

      const canUndo = currentEditingPhoto.historyIndex > 0;
      const canRedo = currentEditingPhoto.historyIndex < currentEditingPhoto.history.length - 1;

      [btnUndo, btnSideUndo].forEach(btn => {
        if (!btn) return;
        btn.disabled = !canUndo;
        btn.classList.toggle('opacity-40', !canUndo);
        btn.classList.toggle('cursor-not-allowed', !canUndo);
      });

      [btnRedo, btnSideRedo].forEach(btn => {
        if (!btn) return;
        btn.disabled = !canRedo;
        btn.classList.toggle('opacity-40', !canRedo);
        btn.classList.toggle('cursor-not-allowed', !canRedo);
      });

      if (histCounter) {
        if (canUndo || canRedo) {
          histCounter.textContent = `(${currentEditingPhoto.historyIndex}/${currentEditingPhoto.history.length - 1})`;
        } else {
          histCounter.textContent = '';
        }
      }
    }

    function getStudioPhotoNavigationList() {
      if (!currentEditingPhoto) return [];
      const book = getActiveBook();
      if (book && book.slots) {
        const bookPhotos = [];
        if (book.slots.cover_front) bookPhotos.push(book.slots.cover_front);
        const backList = Array.isArray(book.slots.cover_back) ? book.slots.cover_back : (book.slots.cover_back ? [book.slots.cover_back] : []);
        backList.forEach(p => bookPhotos.push(p));
        (book.slots.info_pages || []).forEach(p => bookPhotos.push(p));
        (book.slots.illustrations || []).forEach(p => bookPhotos.push(p));
        (book.slots.mantra_defects || []).forEach(p => bookPhotos.push(p));

        const inBook = bookPhotos.some(p => p.id === currentEditingPhoto.id);
        if (inBook) return bookPhotos;
      }
      if (Array.isArray(photoPool) && photoPool.some(p => p.id === currentEditingPhoto.id)) {
        return photoPool;
      }
      return [currentEditingPhoto];
    }

    function updateStudioPhotoNavUI() {
      const counterEl = document.getElementById('studioPhotoCounter');
      const btnPrev = document.getElementById('btnStudioPrevPhoto');
      const btnNext = document.getElementById('btnStudioNextPhoto');
      if (!counterEl) return;

      const list = getStudioPhotoNavigationList();
      if (!list || list.length <= 1) {
        counterEl.textContent = '1 / 1';
        if (btnPrev) {
          btnPrev.disabled = true;
          btnPrev.classList.add('opacity-40', 'cursor-not-allowed');
        }
        if (btnNext) {
          btnNext.disabled = true;
          btnNext.classList.add('opacity-40', 'cursor-not-allowed');
        }
        return;
      }

      const idx = list.findIndex(p => p.id === currentEditingPhoto.id);
      const currentNum = (idx >= 0 ? idx + 1 : 1);
      counterEl.textContent = `${currentNum} / ${list.length}`;

      if (btnPrev) {
        btnPrev.disabled = (idx <= 0);
        btnPrev.classList.toggle('opacity-40', idx <= 0);
        btnPrev.classList.toggle('cursor-not-allowed', idx <= 0);
      }
      if (btnNext) {
        btnNext.disabled = (idx >= list.length - 1);
        btnNext.classList.toggle('opacity-40', idx >= list.length - 1);
        btnNext.classList.toggle('cursor-not-allowed', idx >= list.length - 1);
      }
    }

    function navigateStudioPhoto(direction) {
      if (!currentEditingPhoto) return;
      const list = getStudioPhotoNavigationList();
      if (!list || list.length <= 1) return;
      const idx = list.findIndex(p => p.id === currentEditingPhoto.id);
      if (idx === -1) return;
      const targetIdx = idx + direction;
      if (targetIdx < 0 || targetIdx >= list.length) {
        showToast(direction > 0 ? '🏁 Это последнее фото в книге' : '🏁 Это первое фото в книге');
        return;
      }
      const targetPhoto = list[targetIdx];

      // Если в режиме кадрирования была активна рамка — синхронно фиксируем обрезку без лишней перезагрузки Cropper
      if (isFreeCroppingActive && cropperInstance && cropperInstance.cropped) {
        commitStudioCropToPhotoData();
      }

      if (hasUnsavedStudioChanges) {
        saveStudioChanges(() => {
          openPhotoStudio(targetPhoto.id);
          showToast(`📸 Фото #${targetIdx + 1}: ${targetPhoto.name}`);
        }, true);
      } else {
        openPhotoStudio(targetPhoto.id);
        showToast(`📸 Фото #${targetIdx + 1}: ${targetPhoto.name}`);
      }
    }

    function openPhotoStudio(photoId, e, startMode) {
      if (e) e.stopPropagation();
      const photo = findPhotoById(photoId);
      if (!photo) return;

      // Приостанавливаем упреждающую выгрузку в S3, пока пользователь в редакторе
      if (typeof proactiveS3Timers !== 'undefined' && proactiveS3Timers.has(photo.id)) {
        clearTimeout(proactiveS3Timers.get(photo.id));
        proactiveS3Timers.delete(photo.id);
      }

      currentEditingPhoto = photo;
      if (!photo.cameraOriginal) {
        photo.cameraOriginal = photo.rawOriginal || photo.preview;
      }
      if (!photo.rawOriginal) {
        photo.rawOriginal = photo.cameraOriginal;
      }

      initPhotoHistory(photo);

      isStudioOpen = true;
      hasUnsavedStudioChanges = false;
      updateAiBatchBtnState();

      studioState.whiten = photo.whiten || 0;
      studioState.brightness = photo.brightness || 0;
      studioState.contrast = photo.contrast || 0;
      studioState.saturation = photo.saturation || 0;
      studioCurrentRotation = ((photo.rotation || 0) % 360 + 360) % 360;
      studioBaseCardinal = Math.round(studioCurrentRotation / 90) * 90 % 360;
      studioBaseRotation = studioCurrentRotation;
      studioFineRotation = 0;

      document.getElementById('sliderWhiten').value = studioState.whiten;
      document.getElementById('sliderBrightness').value = studioState.brightness;
      document.getElementById('sliderContrast').value = studioState.contrast;
      document.getElementById('sliderSaturation').value = studioState.saturation;
      initRotaryDial();
      updateRotaryDialUI(studioCurrentRotation);
      updateStudioBadges();

      cropRatio = 'none';
      isFreeCroppingActive = false;
      hasUnsavedCrop = false;
      studioCropBoxOnOriginal = photo.cropBoxOnOriginal ? { ...photo.cropBoxOnOriginal } : null;
      preCropImageSrc = null;
      updateCropRatioButtons('free');
      resetCropStateUI();

      const cropBadge = photo.isCropped ? ' ✂️ [Обрезано]' : '';
      const aiBadge = photo.isAiProcessed ? ' ✨ [ИИ Фон]' : '';
      const slotNames = {
        cover_front: 'Лицевая обложка',
        cover_back: 'Задняя обложка',
        info_pages: 'Титульный лист / инфо',
        illustrations: 'Иллюстрации',
        mantra_defects: 'Дефекты / колофон'
      };
      const slotLabel = photo.assignedSlot ? (slotNames[photo.assignedSlot] || photo.assignedSlot) : 'Общий пул';
      document.getElementById('studioPhotoInfo').textContent = `${photo.name}${cropBadge}${aiBadge} • ${slotLabel}`;
      updateStudioPhotoNavUI();
      updateStudioHistoryUI();

      const isRemote = (s) => typeof s === 'string' && (s.startsWith('http://') || s.startsWith('https://'));

      const hasLocalData = Boolean(
        (photo.croppedBase && !isRemote(photo.croppedBase)) ||
        (photo.aiWhiteOriginal && !isRemote(photo.aiWhiteOriginal)) ||
        (photo.preview && !isRemote(photo.preview)) ||
        (photo.cameraOriginal && !isRemote(photo.cameraOriginal)) ||
        (photo.rawOriginal && !isRemote(photo.rawOriginal)) ||
        photo.data ||
        (photo.url && !isRemote(photo.url))
      );

      const isVaultOrCloud = !hasLocalData && Boolean(
        photo.isFromVault ||
        photo.s3_url ||
        (photo.preview && isRemote(photo.preview)) ||
        (photo.url && isRemote(photo.url))
      );

      const fullSource = getPhotoFullSource(photo);
      const wantCroppedOnOpen = Boolean(photo.isCropped && photo.croppedBase && startMode !== 'crop');

      let baseSource;
      let baseType;

      if (startMode === 'crop') {
        baseSource = fullSource;
        baseType = 'full';
      } else if (wantCroppedOnOpen) {
        baseSource = getSafeStudioSourceUrl(photo.croppedBase);
        baseType = 'cropped';
      } else if (isVaultOrCloud) {
        baseSource = getSafeStudioSourceUrl(photo.s3_url || photo.preview || photo.url);
        baseType = 'cropped';
      } else {
        baseSource = fullSource;
        baseType = 'full';
      }

      // Защитная генерация croppedBase, если флаг isCropped стоял, а среза не было в памяти
      if (photo.isCropped && !photo.croppedBase && startMode !== 'crop' && (photo.cropRelative || photo.aiCropRelative)) {
        const rel = photo.cropRelative || photo.aiCropRelative;
        renderCroppedFromFullSourceAsync(fullSource, studioCurrentRotation, rel).then(cBase => {
          photo.croppedBase = cBase;
          if (currentEditingPhoto && currentEditingPhoto.id === photo.id && cropperInstance && !isFreeCroppingActive) {
            reloadStudioCropper(cBase, () => {
              fitStudioImageToContainer(false);
              cropperInstance.clear();
              cropperInstance.setDragMode('move');
              updateStudioModeUI('move');
              applyStudioFilterPreview();
              updateZoomBadge();
              updateCropResolution();
            }, 'cropped');
          }
        }).catch(() => {});
      }
      document.getElementById('photoStudioModal').classList.remove('hidden');

      reloadStudioCropper(baseSource, () => {
        if (baseType === 'full' && studioCurrentRotation !== 0) {
          cropperInstance.rotateTo(studioCurrentRotation);
        }
        fitStudioImageToContainer(false);
        initStudioSmoothZoom();
        resetCropStateUI();

        if (startMode === 'crop') {
          isFreeCroppingActive = true;
          applyCropAspectRatioToInstance(cropRatio);
          restoreCropFrameOnFullSource(true);
          cropperInstance.setDragMode('move');
          updateStudioModeUI('crop');
        } else {
          isFreeCroppingActive = false;
          if (cropperInstance.cropped) cropperInstance.clear();
          cropperInstance.setDragMode('move');
          updateStudioModeUI('move');
        }

        if (photo.isCropped) {
          updateCropResetButtonVisibility();
        }
        updateCropResolution();
        updateZoomBadge();
        applyStudioFilterPreview();
        updateStudioPhotoNavUI();
        updateStudioHistoryUI();
      }, baseType);
    }

    function reloadStudioCropper(sourceUrl, onReadyCallback, sourceType = 'full') {
      if (cropperInstance) {
        cropperInstance.destroy();
        cropperInstance = null;
      }

      studioLoadedSourceType = sourceType;

      const imgEl = document.getElementById('studioCropperImage');
      if (!imgEl) return;
      imgEl.onload = null;
      imgEl.onerror = null;

      const safeUrl = getSafeStudioSourceUrl(sourceUrl);
      if (safeUrl && (safeUrl.startsWith('http://') || safeUrl.startsWith('https://') || safeUrl.startsWith('/api/image_proxy'))) {
        imgEl.crossOrigin = 'anonymous';
      } else {
        imgEl.removeAttribute('crossOrigin');
      }
      let isHandled = false;

      const onImageLoaded = () => {
        if (isHandled) return;
        isHandled = true;
        imgEl.onload = null;
        imgEl.onerror = null;

        if (cropperInstance) {
          cropperInstance.destroy();
          cropperInstance = null;
        }

        cropperInstance = new Cropper(imgEl, {
          viewMode: 0,
          dragMode: 'move',
          autoCrop: false,
          checkCrossOrigin: false,
          zoomOnWheel: false,
          restore: false,
          guides: true,
          center: true,
          highlight: true,
          cropBoxMovable: true,
          cropBoxResizable: true,
          toggleDragModeOnDblclick: false,
          ready() {
            if (typeof onReadyCallback === 'function') {
              onReadyCallback();
            } else {
              fitStudioImageToContainer(false);
              updateStudioModeUI('move');
              updateZoomBadge();
              updateCropResolution();
              applyStudioFilterPreview();
            }
          },
          crop() {
            updateCropResolution();
          },
          cropmove() {
            if (!isProgrammaticCropBoxUpdate && isFreeCroppingActive && studioLoadedSourceType === 'full') {
              syncCropFrameToPhoto();
            }
            markStudioChanged();
          },
          cropend() {
            if (!isProgrammaticCropBoxUpdate && isFreeCroppingActive && studioLoadedSourceType === 'full' && cropperInstance && cropperInstance.cropped) {
              const savedRel = syncCropFrameToPhoto();
              zoomStudioToCropBox(savedRel);
              recordStudioStep('Изменение рамки');
            }
            updateCropResolution();
            updateCropResetButtonVisibility();
            markStudioChanged();
          },
          zoom() {
            updateZoomBadge();
          }
        });
      };

      imgEl.onerror = (err) => {
        if (isHandled) return;
        isHandled = true;
        imgEl.onload = null;
        imgEl.onerror = null;
        console.error('⚠️ Ошибка загрузки изображения в Studio Cropper:', safeUrl, err);

        // Защитный fallback: пробуем резервные источники по очереди (локальные в приоритете)
        const candidates = [
          currentEditingPhoto?.aiWhiteOriginal,
          currentEditingPhoto?.croppedBase,
          currentEditingPhoto?.preview,
          currentEditingPhoto?.cameraOriginal,
          currentEditingPhoto?.rawOriginal,
          currentEditingPhoto?.data ? `data:image/jpeg;base64,${currentEditingPhoto.data}` : null,
          currentEditingPhoto?.url,
          currentEditingPhoto?.s3_url
        ].filter(Boolean);

        const nextFallback = candidates.find(c => {
          const s = getSafeStudioSourceUrl(c);
          return s && s !== safeUrl;
        });

        if (nextFallback) {
          const fallbackUrl = getSafeStudioSourceUrl(nextFallback);
          console.log('🔄 Fallback Studio Cropper: пробуем резервный источник:', fallbackUrl);
          reloadStudioCropper(fallbackUrl, onReadyCallback, 'fallback');
          return;
        }

        if (typeof showToast === 'function') {
          showToast(`⚠️ Не удалось загрузить фото в редактор: ${escapeHtml((safeUrl || '').slice(0, 50))}`, 'error');
        }
      };

      imgEl.onload = onImageLoaded;
      imgEl.src = safeUrl;

      // Если изображение уже было синхронно декодировано браузером из кэша
      if (imgEl.complete && imgEl.naturalWidth > 0 && !isHandled) {
        setTimeout(onImageLoaded, 15);
      }
    }

    function syncCropFrameToPhoto() {
      if (!cropperInstance || !cropperInstance.cropped || !currentEditingPhoto) return null;
      if (studioLoadedSourceType !== 'full') return currentEditingPhoto.cropRelative || null;

      const canvasData = cropperInstance.getCanvasData();
      const cbData = cropperInstance.getCropBoxData();
      if (canvasData && cbData && canvasData.width > 0 && canvasData.height > 0) {
        const rawX = (cbData.left - canvasData.left) / canvasData.width;
        const rawY = (cbData.top - canvasData.top) / canvasData.height;
        const rawW = cbData.width / canvasData.width;
        const rawH = cbData.height / canvasData.height;

        const rx = Math.max(0, Math.min(0.98, rawX));
        const ry = Math.max(0, Math.min(0.98, rawY));
        const rw = Math.max(0.02, Math.min(1 - rx, rawW));
        const rh = Math.max(0.02, Math.min(1 - ry, rawH));

        const rel = { x: rx, y: ry, w: rw, h: rh };
        currentEditingPhoto.cropRelative = rel;
        currentEditingPhoto.aiCropRelative = rel;
        captureCropBoxOnOriginal();
        currentEditingPhoto.cropBoxOnOriginal = studioCropBoxOnOriginal;
        return rel;
      }
      return currentEditingPhoto.cropRelative || null;
    }

    function applyCropAspectRatioToInstance(mode) {
      if (!cropperInstance) return;
      isProgrammaticCropBoxUpdate = true;
      if (mode === '3:4') {
        cropperInstance.setAspectRatio(3 / 4);
      } else if (mode === '1:1') {
        cropperInstance.setAspectRatio(1);
      } else {
        cropperInstance.setAspectRatio(NaN);
      }
      isProgrammaticCropBoxUpdate = false;
    }

    function getPhotoFullSource(photo) {
      if (!photo) return null;
      const isRemote = (s) => typeof s === 'string' && (s.startsWith('http://') || s.startsWith('https://'));

      // 1. Приоритет быстрым локальным источникам (ИИ белый фон, оригинал камеры, preview, croppedBase, data)
      const localCandidates = [
        photo.aiWhiteOriginal,
        photo.cameraOriginal,
        photo.rawOriginal,
        photo.preview,
        photo.croppedBase,
        photo.data ? `data:image/jpeg;base64,${photo.data}` : null,
        photo.url
      ].filter(Boolean);

      for (const cand of localCandidates) {
        if (!isRemote(cand)) {
          return getSafeStudioSourceUrl(cand);
        }
      }

      // 2. Если локальных источников нет вообще (книга только в облаке Ozon / S3) — используем облачный URL
      const remoteCandidates = [
        photo.s3_url,
        photo.url,
        photo.preview
      ].filter(Boolean);

      for (const cand of remoteCandidates) {
        if (isRemote(cand)) {
          return getSafeStudioSourceUrl(cand);
        }
      }

      return getSafeStudioSourceUrl(localCandidates[0] || photo.preview || photo.url);
    }

    function restoreCropFrameOnFullSource(shouldZoom = true) {
      if (!cropperInstance || !currentEditingPhoto) return false;

      const canvas = cropperInstance.getCanvasData();
      if (!canvas || !canvas.width || !canvas.height) return false;

      let rel = currentEditingPhoto.cropRelative || currentEditingPhoto.aiCropRelative;
      let cbData = null;

      if (rel && rel.w > 0.01 && rel.h > 0.01) {
        const rx = Math.max(0, Math.min(0.98, Number(rel.x) || 0));
        const ry = Math.max(0, Math.min(0.98, Number(rel.y) || 0));
        const rw = Math.max(0.02, Math.min(1 - rx, Number(rel.w) || 1));
        const rh = Math.max(0.02, Math.min(1 - ry, Number(rel.h) || 1));
        rel = { x: rx, y: ry, w: rw, h: rh };

        cbData = {
          left: canvas.left + rx * canvas.width,
          top: canvas.top + ry * canvas.height,
          width: rw * canvas.width,
          height: rh * canvas.height
        };
      } else {
        // Если фото еще ни разу не обрезалось — ставим аккуратную стартовую рамку 94% по центру
        rel = { x: 0.03, y: 0.03, w: 0.94, h: 0.94 };
        cbData = {
          left: canvas.left + rel.x * canvas.width,
          top: canvas.top + rel.y * canvas.height,
          width: rel.w * canvas.width,
          height: rel.h * canvas.height
        };
      }

      cropperInstance.crop();
      isProgrammaticCropBoxUpdate = true;
      cropperInstance.setCropBoxData(cbData);
      isProgrammaticCropBoxUpdate = false;

      currentEditingPhoto.cropRelative = { ...rel };
      currentEditingPhoto.aiCropRelative = { ...rel };
      captureCropBoxOnOriginal();
      currentEditingPhoto.cropBoxOnOriginal = studioCropBoxOnOriginal;

      if (shouldZoom) {
        zoomStudioToCropBox(rel);
      }
      return true;
    }

    function switchToFullSourceForCrop(onReadyCallback) {
      if (!currentEditingPhoto) {
        if (typeof onReadyCallback === 'function') onReadyCallback();
        return;
      }

      const fullSource = getPhotoFullSource(currentEditingPhoto);

      const activateCropOnFull = () => {
        isFreeCroppingActive = true;
        // Сначала показываем панель пропорций, чтобы контейнер принял финальную высоту ДО позиционирования рамки
        updateStudioModeUI('crop');
        if (cropperInstance) {
          cropperInstance.resize();
          if (studioCurrentRotation !== 0) {
            cropperInstance.rotateTo(studioCurrentRotation);
          }
          fitStudioImageToContainer(false);
        }
        applyCropAspectRatioToInstance(cropRatio);
        restoreCropFrameOnFullSource(true);
        cropperInstance.setDragMode('move');
        applyStudioFilterPreview();
        updateCropResolution();
        updateZoomBadge();
        updateCropResetButtonVisibility();
        updateStudioHistoryUI();
        if (typeof onReadyCallback === 'function') onReadyCallback();
      };

      if (studioLoadedSourceType === 'full' && cropperInstance) {
        activateCropOnFull();
        return;
      }

      reloadStudioCropper(fullSource, () => {
        activateCropOnFull();
      }, 'full');
    }

    function updateCropResetButtonVisibility() {
      const btn = document.getElementById('btnResetCrop');
      if (!btn) return;
      const hasCrop = Boolean((cropperInstance && cropperInstance.cropped) || (currentEditingPhoto && (currentEditingPhoto.isCropped || currentEditingPhoto.croppedBase)) || preCropImageSrc);
      if (hasCrop) {
        btn.classList.remove('hidden');
      } else {
        btn.classList.add('hidden');
      }
    }

    function resetCropToOriginal() {
      if (!cropperInstance || !currentEditingPhoto) return;

      const origSrc = getPhotoFullSource(currentEditingPhoto);
      currentEditingPhoto.croppedBase = null;
      currentEditingPhoto.isCropped = false;
      currentEditingPhoto.isAutoCropped = false;
      currentEditingPhoto.aiCropRelative = null;
      currentEditingPhoto.cropRelative = null;
      currentEditingPhoto.cropBoxOnOriginal = null;
      preCropImageSrc = null;
      studioCropBoxOnOriginal = null;
      cropRatio = 'none';
      isFreeCroppingActive = false;

      const finishReset = () => {
        updateCurrentPhotoPreviewFromStudio(() => {
          recordStudioStep('Сброс рамки');
          updateCropRatioButtons('free');
          updateCropResolution();
          updateZoomBadge();
          applyStudioFilterPreview();
          updateCropResetButtonVisibility();
          updateStudioHistoryUI();
          markStudioChanged('Сброс рамки', true);
        });
      };

      if (studioLoadedSourceType !== 'full') {
        reloadStudioCropper(origSrc, () => {
          if (studioCurrentRotation !== 0) {
            cropperInstance.rotateTo(studioCurrentRotation);
          }
          fitStudioImageToContainer(false);
          cropperInstance.clear();
          cropperInstance.setDragMode('move');
          updateStudioModeUI('move');
          finishReset();
        }, 'full');
      } else {
        cropperInstance.clear();
        cropperInstance.setDragMode('move');
        fitStudioImageToContainer(false);
        updateStudioModeUI('move');
        finishReset();
      }
      showToast('↩️ Рамка снята: выбран исходный полный кадр');
    }

    const cancelCropMode = resetCropToOriginal;

    function zoomStudioToCropBox(explicitRel = null) {
      if (!cropperInstance || !cropperInstance.cropped) return;

      const container = cropperInstance.getContainerData();
      const canvas = cropperInstance.getCanvasData();
      const cb = cropperInstance.getCropBoxData();

      if (!cb || !cb.width || !cb.height || cb.width < 15 || cb.height < 15) return;
      if (!container || !container.width || !container.height) return;
      if (!canvas || !canvas.width || !canvas.height) return;

      // Фиксируем точные относительные координаты ДО зума, чтобы избежать малейшего дрейфа
      const rel = (explicitRel && explicitRel.w > 0.01 && explicitRel.h > 0.01)
        ? {
            x: Math.max(0, Math.min(0.98, explicitRel.x)),
            y: Math.max(0, Math.min(0.98, explicitRel.y)),
            w: Math.max(0.02, Math.min(1, explicitRel.w)),
            h: Math.max(0.02, Math.min(1, explicitRel.h))
          }
        : {
            x: Math.max(0, Math.min(0.98, (cb.left - canvas.left) / canvas.width)),
            y: Math.max(0, Math.min(0.98, (cb.top - canvas.top) / canvas.height)),
            w: Math.max(0.02, Math.min(1, cb.width / canvas.width)),
            h: Math.max(0.02, Math.min(1, cb.height / canvas.height))
          };

      // Безопасные отступы от краев экрана и нижней панели
      const safePadX = Math.max(28, Math.round(container.width * 0.035));
      const safePadTop = 20;
      const safePadBottom = 32;

      const availW = Math.max(120, container.width - safePadX * 2);
      const availH = Math.max(120, container.height - safePadTop - safePadBottom);

      // Рамка занимает ~80% безопасной области (~10% видимого исходника с каждой стороны)
      const CROP_SAFE_FRACTION = 0.80;
      const targetCbW = availW * CROP_SAFE_FRACTION;
      const targetCbH = availH * CROP_SAFE_FRACTION;

      const cbScreenW = rel.w * canvas.width;
      const cbScreenH = rel.h * canvas.height;
      let scale = Math.min(targetCbW / cbScreenW, targetCbH / cbScreenH);
      if (!isFinite(scale) || scale <= 0) return;

      // Ограничиваем экстремальный зум (для совсем крошечных областей)
      const imgData = (typeof cropperInstance.getImageData === 'function') ? cropperInstance.getImageData() : {};
      const nw = imgData.naturalWidth || canvas.naturalWidth || canvas.width;
      const nh = imgData.naturalHeight || canvas.naturalHeight || canvas.height;
      const rad = ((studioCurrentRotation || 0) * Math.PI) / 180;
      const rotW = Math.abs(nw * Math.cos(rad)) + Math.abs(nh * Math.sin(rad));
      const rotH = Math.abs(nw * Math.sin(rad)) + Math.abs(nh * Math.cos(rad));
      const aspect = (rotW > 0 && rotH > 0) ? (rotW / rotH) : (availW / availH);
      const baseFitW = (availH * aspect > availW) ? availW : (availH * aspect);
      const maxCanvasW = Math.max(baseFitW * 4.5, availW * 4.5);

      let newCanvasW = canvas.width * scale;
      if (newCanvasW > maxCanvasW) {
        scale = maxCanvasW / canvas.width;
        newCanvasW = maxCanvasW;
      }
      const newCanvasH = canvas.height * scale;

      const newCbW = rel.w * newCanvasW;
      const newCbH = rel.h * newCanvasH;

      // Центрируем рамку строго в безопасной зоне
      const newCbLeft = safePadX + (availW - newCbW) / 2;
      const newCbTop = safePadTop + (availH - newCbH) / 2;

      // Позиционируем холст относительно центрированной рамки по точным rel
      const newCanvasLeft = newCbLeft - rel.x * newCanvasW;
      const newCanvasTop = newCbTop - rel.y * newCanvasH;

      isProgrammaticCropBoxUpdate = true;
      cropperInstance.setCanvasData({
        left: newCanvasLeft,
        top: newCanvasTop,
        width: newCanvasW,
        height: newCanvasH
      });
      cropperInstance.setCropBoxData({
        left: newCbLeft,
        top: newCbTop,
        width: newCbW,
        height: newCbH
      });
      isProgrammaticCropBoxUpdate = false;

      // Сохраняем точные координаты (без накопления погрешностей округления)
      if (currentEditingPhoto) {
        currentEditingPhoto.cropRelative = { ...rel };
        currentEditingPhoto.aiCropRelative = { ...rel };
      }
      captureCropBoxOnOriginal();
      if (currentEditingPhoto) {
        currentEditingPhoto.cropBoxOnOriginal = studioCropBoxOnOriginal;
      }
      updateCropResolution();
      updateZoomBadge();
      updateCropResetButtonVisibility();
    }

    function commitStudioCropToPhotoData() {
      if (!cropperInstance || !currentEditingPhoto || !cropperInstance.cropped) return null;

      const croppedCanvas = cropperInstance.getCroppedCanvas({
        fillColor: '#ffffff',
        imageSmoothingEnabled: true,
        imageSmoothingQuality: 'high'
      });
      if (!croppedCanvas) return null;

      // 1. Сохраняем точные координаты рамки и текущий угол поворота на исходнике
      syncCropFrameToPhoto();
      currentEditingPhoto.rotation = studioCurrentRotation;

      const cleanCroppedUrl = croppedCanvas.toDataURL('image/jpeg', 0.94);

      // 2. Применяем активные фильтры для превью в слотах и пуле
      const filteredCanvas = document.createElement('canvas');
      filteredCanvas.width = croppedCanvas.width;
      filteredCanvas.height = croppedCanvas.height;
      const fCtx = filteredCanvas.getContext('2d');
      fCtx.drawImage(croppedCanvas, 0, 0);
      applyPixelFiltersToCanvas(filteredCanvas, studioState);

      const filteredUrl = filteredCanvas.toDataURL('image/jpeg', 0.92);
      const base64Data = filteredUrl.split(',')[1];

      currentEditingPhoto.croppedBase = cleanCroppedUrl;
      currentEditingPhoto.preview = filteredUrl;
      currentEditingPhoto.data = base64Data;
      currentEditingPhoto.mime = 'image/jpeg';
      currentEditingPhoto.isCropped = true;
      currentEditingPhoto.isProcessed = true;
      currentEditingPhoto.is_s3_uploaded = false;
      currentEditingPhoto.s3_url = null;

      isFreeCroppingActive = false;

      // Записываем завершенный шаг обрезки в историю (inCropMode: false)
      recordStudioStep('Обрезка кадра');

      renderPool();
      renderActiveBookSlots();
      scheduleAutoSave();

      return cleanCroppedUrl;
    }

    function commitStudioCrop(onDoneCallback) {
      if (!cropperInstance || !currentEditingPhoto) {
        if (typeof onDoneCallback === 'function') onDoneCallback();
        return;
      }

      if (cropperInstance.cropped) {
        const cleanCroppedUrl = commitStudioCropToPhotoData();
        if (cleanCroppedUrl) {
          reloadStudioCropper(cleanCroppedUrl, () => {
            fitStudioImageToContainer(false);
            cropperInstance.clear();
            cropperInstance.setDragMode('move');
            updateStudioModeUI('move');
            updateRotaryDialUI(studioCurrentRotation);
            updateZoomBadge();
            updateCropResolution();
            applyStudioFilterPreview();
            updateCropResetButtonVisibility();
            updateStudioHistoryUI();
            showToast('✂️ Картинка зафиксирована в области среза!');
            if (typeof onDoneCallback === 'function') onDoneCallback();
          }, 'cropped');
          return;
        }
      }

      isFreeCroppingActive = false;
      cropperInstance.setDragMode('move');
      updateStudioModeUI('move');
      if (typeof onDoneCallback === 'function') onDoneCallback();
    }

    const confirmAndApplyCrop = commitStudioCrop;
    const applyCropDirectly = commitStudioCrop;

    function resetCropSelectionUI() {
      updateCropResetButtonVisibility();
    }

    function resetCropStateUI() {
      const qr = document.getElementById('cropRatioQuickRow');
      if (qr) qr.classList.add('hidden');

      const crs = document.getElementById('studioCropRightSection');
      if (crs) crs.classList.add('hidden');

      updateCropResetButtonVisibility();

      const hint = document.getElementById('studioCropHint');
      if (hint) {
        hint.innerHTML = '✋ <b>Режим перемещения</b>: зажмите мышь и двигайте фото в окне. Колесико мыши — плавный зум.';
      }
    }

    function cancelCropSelection() {
      if (!cropperInstance) return;
      studioCropBoxOnOriginal = null;
      cropperInstance.clear();
      isFreeCroppingActive = false;
      updateStudioModeUI('move');
      resetCropSelectionUI();
      updateCropResolution();
      showToast('✕ Выделение сброшено');
    }

    function updateCropResolution() {
      if (!cropperInstance) return;
      const resEl = document.getElementById('studioResolutionText');
      if (!resEl) return;
      if (cropperInstance.cropped) {
        const data = cropperInstance.getData(true);
        if (data && data.width && data.height) {
          const w = Math.round(data.width);
          const h = Math.round(data.height);
          let ratioLabel = '';
          if (cropRatio === '3:4') ratioLabel = ' (3:4)';
          else if (cropRatio === '1:1') ratioLabel = ' (1:1)';
          resEl.textContent = `✂️ Рамка: ${w} × ${h} px${ratioLabel}`;
        }
      } else {
        const canvasData = cropperInstance.getCanvasData();
        const w = Math.round(canvasData.naturalWidth || canvasData.width || 0);
        const h = Math.round(canvasData.naturalHeight || canvasData.height || 0);
        resEl.textContent = (w && h) ? `🖼️ Кадр: ${w} × ${h} px` : 'Весь кадр';
      }
    }

    function closePhotoStudio(saveBeforeClose = false) {
      // Если закрываем модалку находясь в режиме кадрирования с рамкой — синхронно фиксируем обрезку
      if (isFreeCroppingActive && cropperInstance && cropperInstance.cropped) {
        commitStudioCropToPhotoData();
      }

      if (saveBeforeClose && currentEditingPhoto && cropperInstance && hasUnsavedStudioChanges) {
        saveStudioChanges(null, false);
        return;
      }

      if (cropperInstance) {
        cropperInstance.destroy();
        cropperInstance = null;
      }

      const modal = document.getElementById('photoStudioModal');
      if (modal) modal.classList.add('hidden');

      const closedPhoto = currentEditingPhoto;
      currentEditingPhoto = null;
      hasUnsavedStudioChanges = false;
      isStudioOpen = false;
      isFreeCroppingActive = false;
      updateAiBatchBtnState();

      // Планируем фоновую выгрузку в S3, если фото назначено в слот
      if (closedPhoto && closedPhoto.assignedSlot && typeof scheduleProactiveS3Upload === 'function') {
        scheduleProactiveS3Upload(closedPhoto.id, closedPhoto.assignedSlot, 2500);
      }
    }

    function updateStudioBadges() {
      document.getElementById('valWhiten').textContent = `${studioState.whiten}%`;
      document.getElementById('valBrightness').textContent = `${studioState.brightness > 0 ? '+' : ''}${studioState.brightness}%`;
      document.getElementById('valContrast').textContent = `${studioState.contrast > 0 ? '+' : ''}${studioState.contrast}%`;
      document.getElementById('valSaturation').textContent = `${studioState.saturation > 0 ? '+' : ''}${studioState.saturation}%`;
    }

    function updateCropRatioButtons(activeMode) {
      const normalized = (!activeMode || activeMode === 'none') ? 'free' : activeMode;
      const pairs = [
        { key: 'free', btns: ['ratioBtn_free', 'ratioBtnSide_free'] },
        { key: '3:4',  btns: ['ratioBtn_34', 'ratioBtnSide_34'] },
        { key: '1:1',  btns: ['ratioBtn_11', 'ratioBtnSide_11'] }
      ];
      pairs.forEach(p => {
        const isActive = (p.key === normalized);
        p.btns.forEach(id => {
          const btn = document.getElementById(id);
          if (!btn) return;
          if (id.startsWith('ratioBtn_')) {
            btn.className = isActive
              ? 'crop-ratio-btn py-0.5 px-2 rounded-lg bg-amber-600 text-white text-[11px] font-bold transition shadow-sm'
              : 'crop-ratio-btn py-0.5 px-2 rounded-lg bg-slate-800 hover:bg-slate-750 text-slate-300 text-[11px] font-medium transition';
          } else {
            btn.className = isActive
              ? 'crop-ratio-btn py-1.5 rounded-lg bg-amber-600 text-white font-bold transition text-center shadow-sm'
              : 'crop-ratio-btn py-1.5 rounded-lg bg-slate-800 hover:bg-slate-750 text-slate-300 font-medium transition text-center';
          }
        });
      });
    }

    function updateStudioModeUI(mode) {
      const btnMove = document.getElementById('btnModeMove');
      const btnCrop = document.getElementById('btnModeCrop');
      const btnCropText = document.getElementById('btnModeCropText');
      const qr = document.getElementById('cropRatioQuickRow');
      const crs = document.getElementById('studioCropRightSection');
      const hint = document.getElementById('studioCropHint');

      if (mode === 'crop') {
        if (btnMove) {
          btnMove.className = 'py-1 px-2.5 rounded-lg text-[11px] font-medium transition flex items-center gap-1.5 bg-slate-800 hover:bg-slate-750 text-slate-300';
        }
        if (btnCrop) {
          btnCrop.className = 'py-1 px-2.5 rounded-lg text-[11px] font-bold transition flex items-center gap-1.5 bg-amber-600 hover:bg-amber-500 text-white shadow-md ring-1 ring-amber-400/50';
        }
        if (btnCropText) {
          btnCropText.textContent = 'Выйти из среза';
        }
        if (qr) qr.classList.remove('hidden');
        if (crs) crs.classList.remove('hidden');
        if (hint) {
          hint.innerHTML = '✂️ <b>Режим среза</b>: тяните углы/края рамки, фон снаружи двигает фото (не сбрасывает рамку). <b>[C]</b> — зафиксировать.';
        }
        updateCropRatioButtons(cropRatio);
      } else {
        if (btnMove) {
          btnMove.className = 'py-1 px-2.5 rounded-lg text-[11px] font-bold transition flex items-center gap-1.5 bg-amber-600 text-white shadow-sm';
        }
        if (btnCrop) {
          btnCrop.className = 'py-1 px-2.5 rounded-lg text-[11px] font-medium transition flex items-center gap-1.5 bg-slate-800 hover:bg-slate-750 text-slate-300';
        }
        if (btnCropText) {
          btnCropText.textContent = 'Срез';
        }
        if (qr) qr.classList.add('hidden');
        if (crs) crs.classList.add('hidden');
        if (hint) {
          hint.innerHTML = '✋ <b>Режим перемещения</b>: зажмите мышь и двигайте фото в окне. Колесико мыши — плавный зум. Нажмите <b>[C]</b> для обрезания.';
        }
      }
      updateCropResolution();
      updateCropResetButtonVisibility();
    }

    function setStudioInteractionMode(mode) {
      if (!cropperInstance) return;

      if (mode === 'crop') {
        switchToFullSourceForCrop();
      } else {
        // Если переходим в режим перемещения из активного режима кадрирования с рамкой —
        // фиксируем картинку в рамке!
        if (isFreeCroppingActive && cropperInstance && cropperInstance.cropped) {
          commitStudioCrop();
          return;
        }

        isFreeCroppingActive = false;
        cropperInstance.setDragMode('move');
        updateStudioModeUI('move');
      }
    }

    function toggleStudioCropMode() {
      if (!cropperInstance) return;
      if (isFreeCroppingActive) {
        if (cropperInstance.cropped) {
          commitStudioCrop();
        } else {
          setStudioInteractionMode('move');
          showToast('✋ Режим перемещения активен');
        }
      } else {
        switchToFullSourceForCrop(() => {
          showToast('✂️ Режим среза: границы рамки сохранены, фон вокруг виден');
        });
      }
    }

    function initStudioSmoothZoom() {
      const container = document.getElementById('studioCropperContainer');
      if (!container || container.dataset.smoothZoomInit) return;
      container.dataset.smoothZoomInit = 'true';

      container.addEventListener('wheel', (e) => {
        e.preventDefault();
        if (!cropperInstance) return;

        let delta = -e.deltaY;
        if (e.deltaMode === 1) delta *= 25;
        else if (e.deltaMode === 2) delta *= 500;

        const clamped = Math.max(-60, Math.min(60, delta));
        const zoomStep = clamped * 0.0018;

        if (Math.abs(zoomStep) > 0.001) {
          cropperInstance.zoom(zoomStep);
          updateZoomBadge();
        }
      }, { passive: false });

      // Двойной клик: если была рамка — подтверждает обрезку, если рамки нет — центрирует кадр
      container.addEventListener('dblclick', (e) => {
        if (!cropperInstance) return;
        if (cropperInstance.cropped) {
          const data = cropperInstance.getData(true);
          if (data && data.width > 20 && data.height > 20) {
            e.preventDefault();
            e.stopPropagation();
            confirmAndApplyCrop();
            return;
          }
        }
        e.preventDefault();
        centerStudioImage();
      });

      setupStudioResizeObserver();
    }

    let studioResizeObserver = null;
    let lastObservedContainerW = 0;
    let lastObservedContainerH = 0;

    function handleStudioContainerResize() {
      if (!isStudioOpen || !cropperInstance) return;
      const savedRel = (currentEditingPhoto && (currentEditingPhoto.cropRelative || currentEditingPhoto.aiCropRelative))
        ? { ...(currentEditingPhoto.cropRelative || currentEditingPhoto.aiCropRelative) }
        : null;
      const wasCropping = Boolean(isFreeCroppingActive && studioLoadedSourceType === 'full');

      // cropper.resize() при restore:false сбрасывает холст и рамку на 80% по умолчанию,
      // поэтому сразу восстанавливаем угол поворота и сохраненную рамку!
      cropperInstance.resize();

      if (studioLoadedSourceType === 'full' && studioCurrentRotation !== 0) {
        cropperInstance.rotateTo(studioCurrentRotation);
      }

      if (wasCropping) {
        fitStudioImageToContainer(false);
        if (savedRel && currentEditingPhoto) {
          currentEditingPhoto.cropRelative = { ...savedRel };
          currentEditingPhoto.aiCropRelative = { ...savedRel };
        }
        applyCropAspectRatioToInstance(cropRatio);
        restoreCropFrameOnFullSource(true);
        cropperInstance.setDragMode('move');
      } else {
        fitStudioImageToContainer(false);
        if (cropperInstance.cropped) cropperInstance.clear();
      }
      applyStudioFilterPreview();
      updateZoomBadge();
      updateCropResolution();
    }

    function setupStudioResizeObserver() {
      const container = document.getElementById('studioCropperContainer');
      if (!container || studioResizeObserver) return;
      if (typeof ResizeObserver === 'undefined') return;

      studioResizeObserver = new ResizeObserver((entries) => {
        if (!isStudioOpen || !cropperInstance) return;
        for (const entry of entries) {
          const w = Math.round(entry.contentRect.width);
          const h = Math.round(entry.contentRect.height);
          if (w > 50 && h > 50 && (w !== lastObservedContainerW || h !== lastObservedContainerH)) {
            lastObservedContainerW = w;
            lastObservedContainerH = h;
            handleStudioContainerResize();
          }
        }
      });
      studioResizeObserver.observe(container);
    }

    function updateZoomBadge() {
      if (!cropperInstance) return;
      const canvasData = cropperInstance.getCanvasData();
      const badge = document.getElementById('studioZoomBadge');
      if (badge && canvasData && canvasData.naturalWidth) {
        const pct = Math.round((canvasData.width / canvasData.naturalWidth) * 100);
        badge.textContent = `${pct}%`;
      }
    }

    function zoomStudio(delta) {
      if (!cropperInstance) return;
      cropperInstance.zoom(delta);
      updateZoomBadge();
    }

    function centerStudioImage() {
      if (!cropperInstance) return;
      if (cropperInstance.cropped && isFreeCroppingActive) {
        zoomStudioToCropBox(currentEditingPhoto ? currentEditingPhoto.cropRelative : null);
      } else {
        fitStudioImageToContainer(false);
      }
      updateZoomBadge();
      showToast('🎯 Фото выровнено строго по центру');
    }

    function startFreeCrop() {
      if (!cropperInstance) return;
      studioCropBoxOnOriginal = null;
      cropperInstance.clear();
      setStudioInteractionMode('crop');
      const normDeg = ((studioCurrentRotation % 360) + 360) % 360;
      const nearestCardinal = Math.round(normDeg / 90) * 90 % 360;
      const isPerp = (nearestCardinal === 90 || nearestCardinal === 270);
      cropperInstance.setAspectRatio(cropRatio === '3:4' ? (isPerp ? 4/3 : 3/4) : (cropRatio === '1:1' ? 1 : NaN));
      markStudioChanged();
    }

    const saveCropOnly = saveStudioChanges;

    function fitBookToOzonFrame() {
      if (!cropperInstance || !currentEditingPhoto) return;

      try {
        const srcCanvas = cropperInstance.getCroppedCanvas({
          fillColor: '#ffffff',
          imageSmoothingEnabled: true,
          imageSmoothingQuality: 'high'
        });
        if (!srcCanvas) return;

        // Ozon standard card: 1200 x 1600 (3:4 ratio)
        const targetW = 1200;
        const targetH = 1600;
        const ozonCanvas = document.createElement('canvas');
        ozonCanvas.width = targetW;
        ozonCanvas.height = targetH;
        const ctx = ozonCanvas.getContext('2d');

        // 1. Fill background with pure studio white
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, 0, targetW, targetH);

        // 2. Scale book to fit 88% of canvas height/width with 6% clean margins
        const maxBookW = targetW * 0.88;
        const maxBookH = targetH * 0.88;
        const bookAspect = srcCanvas.width / srcCanvas.height;

        let drawW, drawH;
        if (bookAspect > (maxBookW / maxBookH)) {
          drawW = maxBookW;
          drawH = drawW / bookAspect;
        } else {
          drawH = maxBookH;
          drawW = drawH * bookAspect;
        }

        const drawX = (targetW - drawW) / 2;
        const drawY = (targetH - drawH) / 2;

        ctx.imageSmoothingEnabled = true;
        ctx.imageSmoothingQuality = 'high';
        ctx.drawImage(srcCanvas, drawX, drawY, drawW, drawH);

        const imgEl = document.getElementById('studioCropperImage');
        if (!preCropImageSrc) {
          preCropImageSrc = imgEl ? imgEl.src : (currentEditingPhoto.croppedBase || currentEditingPhoto.cameraOriginal || currentEditingPhoto.preview);
        }

        const framedUrl = ozonCanvas.toDataURL('image/jpeg', 0.95);
        currentEditingPhoto.croppedBase = framedUrl;
        currentEditingPhoto.isCropped = true;
        hasUnsavedCrop = true;

        studioBaseCardinal = 0;
        setStudioRotation(0, false, false);

        reloadStudioCropper(framedUrl, () => {
          fitStudioImageToContainer(false);
          setStudioInteractionMode('move');
          updateZoomBadge();
          updateCropResolution();
          applyStudioFilterPreview();
          updateCropResetButtonVisibility();
        });

        markStudioChanged();
        showToast('📐 Книга ровно вписана по центру на белом фоне 3:4 Ozon');
      } catch (err) {
        console.error('Ошибка вписывания в Ozon 3:4:', err);
      }
    }

    function screenToOriginal(cb, canvas, img, deg) {
      if (!cb || !canvas || !img) return null;
      const rad = deg * Math.PI / 180;
      const cos = Math.cos(rad);
      const sin = Math.sin(rad);

      const scale = canvas.width / canvas.naturalWidth;
      if (!scale || !isFinite(scale) || scale <= 0) return null;

      const canvasCx = canvas.left + canvas.width / 2;
      const canvasCy = canvas.top + canvas.height / 2;

      const cbCx = cb.left + cb.width / 2;
      const cbCy = cb.top + cb.height / 2;

      const rotDx = (cbCx - canvasCx) / scale;
      const rotDy = (cbCy - canvasCy) / scale;

      // Обратная матрица поворота: [cos, sin; -sin, cos]
      const origDx = rotDx * cos + rotDy * sin;
      const origDy = -rotDx * sin + rotDy * cos;

      const nw = img.naturalWidth;
      const nh = img.naturalHeight;

      const origCx = nw / 2 + origDx;
      const origCy = nh / 2 + origDy;

      const normDeg = ((deg % 360) + 360) % 360;
      const nearestCardinal = Math.round(normDeg / 90) * 90 % 360;
      const isPerp = (nearestCardinal === 90 || nearestCardinal === 270);
      const origW = (isPerp ? cb.height : cb.width) / scale;
      const origH = (isPerp ? cb.width : cb.height) / scale;

      return {
        x: origCx - origW / 2,
        y: origCy - origH / 2,
        w: origW,
        h: origH
      };
    }

    function originalToScreen(orig, canvas, img, deg) {
      if (!orig || !canvas || !img) return null;
      const rad = deg * Math.PI / 180;
      const cos = Math.cos(rad);
      const sin = Math.sin(rad);

      const scale = canvas.width / canvas.naturalWidth;
      if (!scale || !isFinite(scale) || scale <= 0) return null;

      const canvasCx = canvas.left + canvas.width / 2;
      const canvasCy = canvas.top + canvas.height / 2;

      const nw = img.naturalWidth;
      const nh = img.naturalHeight;

      const origCx = orig.x + orig.w / 2;
      const origCy = orig.y + orig.h / 2;

      const origDx = origCx - nw / 2;
      const origDy = origCy - nh / 2;

      // Прямой поворот точки центра:
      const rotDx = origDx * cos - origDy * sin;
      const rotDy = origDx * sin + origDy * cos;

      const screenCx = canvasCx + rotDx * scale;
      const screenCy = canvasCy + rotDy * scale;

      const sw = (orig.w * Math.abs(cos) + orig.h * Math.abs(sin)) * scale;
      const sh = (orig.w * Math.abs(sin) + orig.h * Math.abs(cos)) * scale;

      let left = screenCx - sw / 2;
      let top = screenCy - sh / 2;

      left = Math.max(canvas.left, Math.min(canvas.left + canvas.width - sw, left));
      top = Math.max(canvas.top, Math.min(canvas.top + canvas.height - sh, top));

      return {
        left: left,
        top: top,
        width: Math.min(canvas.width, sw),
        height: Math.min(canvas.height, sh)
      };
    }

    function captureCropBoxOnOriginal() {
      if (!cropperInstance || !cropperInstance.cropped) return;
      const cb = cropperInstance.getCropBoxData();
      const canvas = cropperInstance.getCanvasData();
      const img = cropperInstance.getImageData();
      if (!cb || !cb.width || !cb.height || !canvas || !img) return;

      studioCropBoxOnOriginal = screenToOriginal(cb, canvas, img, studioCurrentRotation);
    }

    function updateCropBoxForCurrentRotation(customCanvasData = null) {
      if (!cropperInstance || !cropperInstance.cropped || !studioCropBoxOnOriginal) return;

      const canvas = customCanvasData || cropperInstance.getCanvasData();
      const img = cropperInstance.getImageData();
      if (!canvas || !canvas.width || !img || !img.naturalWidth) return;

      const newCb = originalToScreen(studioCropBoxOnOriginal, canvas, img, studioCurrentRotation);
      if (newCb && newCb.width > 10 && newCb.height > 10) {
        isProgrammaticCropBoxUpdate = true;
        const oldAspectRatio = cropperInstance.options.aspectRatio;
        cropperInstance.options.aspectRatio = NaN;
        cropperInstance.setCropBoxData(newCb);

        const normDeg = ((studioCurrentRotation % 360) + 360) % 360;
        const nearestCardinal = Math.round(normDeg / 90) * 90 % 360;
        const isPerp = (nearestCardinal === 90 || nearestCardinal === 270);
        let restoredRatio = NaN;
        if (cropRatio === '3:4') {
          restoredRatio = isPerp ? 4/3 : 3/4;
        } else if (cropRatio === '1:1') {
          restoredRatio = 1;
        }
        cropperInstance.options.aspectRatio = restoredRatio;

        isProgrammaticCropBoxUpdate = false;
        updateCropResolution();
      }
    }

    function fitStudioImageToContainer(resetCropBox = false) {
      if (!cropperInstance) return;
      const containerData = cropperInstance.getContainerData();
      const cw = containerData.width;
      const ch = containerData.height;
      if (!cw || !ch) return;

      const canvasData = cropperInstance.getCanvasData();
      const imgData = (typeof cropperInstance.getImageData === 'function') ? cropperInstance.getImageData() : {};
      const nw = imgData.naturalWidth || canvasData.naturalWidth || canvasData.width;
      const nh = imgData.naturalHeight || canvasData.naturalHeight || canvasData.height;
      if (!nw || !nh) return;

      // Если в Cropper загружен уже нарезанный croppedBase, он уже повернут (внутренний угол Cropper = 0°)
      const effectiveRot = (studioLoadedSourceType === 'cropped') ? 0 : (studioCurrentRotation || 0);
      const rad = (effectiveRot * Math.PI) / 180;
      const rotW = Math.abs(nw * Math.cos(rad)) + Math.abs(nh * Math.sin(rad));
      const rotH = Math.abs(nw * Math.sin(rad)) + Math.abs(nh * Math.cos(rad));
      const aspect = (rotW > 0 && rotH > 0) ? (rotW / rotH) : (cw / ch);

      // Комфортные безопасные отступы со всех сторон и гарантированный зазор над нижней панелью
      const padX = 36;
      const padTop = 24;
      const padBottom = 36;
      const maxW = Math.max(80, cw - padX * 2);
      const maxH = Math.max(80, ch - padTop - padBottom);

      let fitW, fitH;
      if (maxH * aspect > maxW) {
        fitW = maxW;
        fitH = fitW / aspect;
      } else {
        fitH = maxH;
        fitW = fitH * aspect;
      }

      const fitLeft = (cw - fitW) / 2;
      const fitTop = padTop + (maxH - fitH) / 2;

      const wasCropped = Boolean(cropperInstance.cropped);

      if (!wasCropped) {
        cropperInstance.setCanvasData({
          left: fitLeft,
          top: fitTop,
          width: fitW,
          height: fitH
        });
        updateCropResolution();
        return;
      }

      const prevCanvas = { ...canvasData };
      const prevBox = cropperInstance.getCropBoxData();

      cropperInstance.setCanvasData({
        left: fitLeft,
        top: fitTop,
        width: fitW,
        height: fitH
      });

      if (!resetCropBox && prevBox && prevBox.width > 20 && prevCanvas.width > 0) {
        const rx = (prevBox.left - prevCanvas.left) / prevCanvas.width;
        const ry = (prevBox.top - prevCanvas.top) / prevCanvas.height;
        const rw = prevBox.width / prevCanvas.width;
        const rh = prevBox.height / prevCanvas.height;

        isProgrammaticCropBoxUpdate = true;
        cropperInstance.setCropBoxData({
          left: fitLeft + rx * fitW,
          top: fitTop + ry * fitH,
          width: Math.min(fitW, rw * fitW),
          height: Math.min(fitH, rh * fitH)
        });
        isProgrammaticCropBoxUpdate = false;
        syncCropFrameToPhoto();
      } else if (resetCropBox) {
        isProgrammaticCropBoxUpdate = true;
        cropperInstance.setCropBoxData({
          left: fitLeft,
          top: fitTop,
          width: fitW,
          height: fitH
        });
        isProgrammaticCropBoxUpdate = false;
        syncCropFrameToPhoto();
      }

      updateCropResolution();
    }

    function applyStudioFilterPreview() {
      const b = 1 + (studioState.brightness / 100);
      const c = 1 + (studioState.contrast / 100);
      const s = 1 + (studioState.saturation / 100);
      const wFactor = studioState.whiten > 0 ? (1 + (studioState.whiten / 200)) : 1;
      const filterStr = `brightness(${(b * wFactor).toFixed(2)}) contrast(${c.toFixed(2)}) saturate(${s.toFixed(2)})`;
      const imgs = document.querySelectorAll('#studioCropperContainer img');
      imgs.forEach(img => { img.style.filter = filterStr; });
    }

    function updateStudioFromSliders() {
      studioState.whiten = parseInt(document.getElementById('sliderWhiten').value) || 0;
      studioState.brightness = parseInt(document.getElementById('sliderBrightness').value) || 0;
      studioState.contrast = parseInt(document.getElementById('sliderContrast').value) || 0;
      studioState.saturation = parseInt(document.getElementById('sliderSaturation').value) || 0;
      updateStudioBadges();
      applyStudioFilterPreview();
      markStudioChanged('Фильтры', false);
    }

    function applyStudioPreset(presetName) {
      if (presetName === 'sharp_text') {
        studioState.whiten = 0;
        studioState.brightness = 3;
        studioState.contrast = 18;
        studioState.saturation = 0;
      } else if (presetName === 'vibrant_art') {
        studioState.whiten = 0;
        studioState.brightness = 0;
        studioState.contrast = 8;
        studioState.saturation = 15;
      } else if (presetName === 'clean_white') {
        studioState.whiten = 75;
        studioState.brightness = 2;
        studioState.contrast = 5;
        studioState.saturation = 0;
      } else if (presetName === 'original') {
        studioState.whiten = 0;
        studioState.brightness = 0;
        studioState.contrast = 0;
        studioState.saturation = 0;
      }

      document.getElementById('sliderWhiten').value = studioState.whiten;
      document.getElementById('sliderBrightness').value = studioState.brightness;
      document.getElementById('sliderContrast').value = studioState.contrast;
      document.getElementById('sliderSaturation').value = studioState.saturation;
      updateStudioBadges();
      applyStudioFilterPreview();

      updateCurrentPhotoPreviewFromStudio(() => {
        recordStudioStep('Пресет: ' + presetName);
        markStudioChanged('Пресет: ' + presetName);
      });
    }

    function setStudioRotation(deg, fitToContainer = false, pushHistory = false) {
      let normalized = ((deg % 360) + 360) % 360;
      normalized = Math.round(normalized * 10) / 10;
      studioCurrentRotation = normalized;
      studioBaseRotation = normalized;

      updateRotaryDialUI(studioCurrentRotation);

      // Поворачиваем холст Cropper.js только когда в нем загружен полный исходник
      if (cropperInstance && studioLoadedSourceType === 'full') {
        cropperInstance.rotateTo(studioCurrentRotation);

        if (fitToContainer) {
          fitStudioImageToContainer(false);
        }
      }

      if (pushHistory && currentEditingPhoto) {
        currentEditingPhoto.rotation = studioCurrentRotation;
        recordStudioStep(`Поворот на ${studioCurrentRotation}°`);
      }
    }

    let rotationAnimationId = null;

    function animateStudioRotation(targetAngle, durationMs = 280, onComplete) {
      if (rotationAnimationId) {
        cancelAnimationFrame(rotationAnimationId);
        rotationAnimationId = null;
      }

      const startAngle = studioCurrentRotation;
      let diff = targetAngle - startAngle;
      while (diff > 180) diff -= 360;
      while (diff < -180) diff += 360;

      if (Math.abs(diff) < 0.2) {
        setStudioRotation(targetAngle, true, false);
        if (typeof onComplete === 'function') onComplete();
        return;
      }

      const startTime = performance.now();

      function step(now) {
        const elapsed = now - startTime;
        const progress = Math.min(1, elapsed / durationMs);
        const easeOut = 1 - Math.pow(1 - progress, 3);
        const currentDeg = startAngle + diff * easeOut;

        setStudioRotation(currentDeg, false, false);

        if (progress < 1) {
          rotationAnimationId = requestAnimationFrame(step);
        } else {
          rotationAnimationId = null;
          setStudioRotation(targetAngle, true, false);
          if (typeof onComplete === 'function') onComplete();
        }
      }

      rotationAnimationId = requestAnimationFrame(step);
    }

    function rotateStudioStep(direction) {
      if (!currentEditingPhoto || !cropperInstance) return;

      // Вычисляем новый кардинальный угол (+90° или -90°)
      const newCardinal = direction > 0
        ? (studioBaseCardinal + 90) % 360
        : (studioBaseCardinal - 90 + 360) % 360;
      studioBaseCardinal = newCardinal;

      // Ветка A: Фото сейчас в режиме просмотра чистого среза ('cropped')
      if (studioLoadedSourceType === 'cropped' && currentEditingPhoto.isCropped) {
        studioCurrentRotation = newCardinal;
        studioBaseRotation = newCardinal;
        currentEditingPhoto.rotation = newCardinal;
        updateRotaryDialUI(newCardinal);

        if (currentEditingPhoto.cropRelative) {
          currentEditingPhoto.cropRelative = transformCropRelativeBy90(currentEditingPhoto.cropRelative, direction);
          currentEditingPhoto.aiCropRelative = currentEditingPhoto.cropRelative;
        }

        const fullSource = getPhotoFullSource(currentEditingPhoto);
        renderCroppedFromFullSourceAsync(fullSource, newCardinal, currentEditingPhoto.cropRelative).then(newCroppedBase => {
          if (!currentEditingPhoto) return;
          currentEditingPhoto.croppedBase = newCroppedBase;
          return applyFiltersToImageAsync(newCroppedBase, studioState).then(filteredUrl => {
            if (!currentEditingPhoto) return;
            currentEditingPhoto.preview = filteredUrl;
            currentEditingPhoto.data = filteredUrl.includes(',') ? filteredUrl.split(',')[1] : filteredUrl;
            currentEditingPhoto.isProcessed = true;
            currentEditingPhoto.is_s3_uploaded = false;
            currentEditingPhoto.s3_url = null;

            recordStudioStep(`Поворот на ${newCardinal}°`);
            renderPool();
            renderActiveBookSlots();
            scheduleAutoSave();

            reloadStudioCropper(newCroppedBase, () => {
              fitStudioImageToContainer(false);
              cropperInstance.clear();
              cropperInstance.setDragMode('move');
              updateStudioModeUI('move');
              updateRotaryDialUI(newCardinal);
              applyStudioFilterPreview();
              updateZoomBadge();
              updateCropResolution();
              updateStudioHistoryUI();
            }, 'cropped');
          });
        }).catch(err => console.warn('Ошибка поворота обрезанного кадра:', err));
        return;
      }

      // Ветка B: Фото открыто на полном исходнике (в «Срезе» или необрезанное в «Двигать»)
      let relCrop = null;
      if (cropperInstance.cropped) {
        const curRel = syncCropFrameToPhoto();
        if (curRel) {
          relCrop = transformCropRelativeBy90(curRel, direction);
        }
      }

      animateStudioRotation(newCardinal, 260, () => {
        if (!currentEditingPhoto || !cropperInstance) return;
        currentEditingPhoto.rotation = newCardinal;

        if (relCrop && cropperInstance.cropped) {
          const nc = cropperInstance.getCanvasData();
          if (nc && nc.width > 0 && nc.height > 0) {
            isProgrammaticCropBoxUpdate = true;
            cropperInstance.setCropBoxData({
              left: nc.left + relCrop.x * nc.width,
              top: nc.top + relCrop.y * nc.height,
              width: relCrop.w * nc.width,
              height: relCrop.h * nc.height
            });
            isProgrammaticCropBoxUpdate = false;
            currentEditingPhoto.cropRelative = { ...relCrop };
            currentEditingPhoto.aiCropRelative = { ...relCrop };
            zoomStudioToCropBox(relCrop);
          }
          recordStudioStep(`Поворот на ${newCardinal}°`);
          markStudioChanged(`Поворот на ${newCardinal}°`, true);
        } else {
          updateCurrentPhotoPreviewFromStudio(() => {
            recordStudioStep(`Поворот на ${newCardinal}°`);
            markStudioChanged(`Поворот на ${newCardinal}°`, true);
          });
        }
      });
    }

    const rotateStudio = (deg) => rotateStudioStep(deg > 0 ? 1 : -1);

    function resetStudioRotation() {
      if (!currentEditingPhoto || !cropperInstance) return;
      studioBaseCardinal = 0;

      if (studioLoadedSourceType === 'cropped' && currentEditingPhoto.isCropped) {
        studioCurrentRotation = 0;
        studioBaseRotation = 0;
        currentEditingPhoto.rotation = 0;
        updateRotaryDialUI(0);

        const fullSource = getPhotoFullSource(currentEditingPhoto);
        renderCroppedFromFullSourceAsync(fullSource, 0, currentEditingPhoto.cropRelative).then(newCroppedBase => {
          if (!currentEditingPhoto) return;
          currentEditingPhoto.croppedBase = newCroppedBase;
          return applyFiltersToImageAsync(newCroppedBase, studioState).then(filteredUrl => {
            if (!currentEditingPhoto) return;
            currentEditingPhoto.preview = filteredUrl;
            currentEditingPhoto.data = filteredUrl.includes(',') ? filteredUrl.split(',')[1] : filteredUrl;
            recordStudioStep('Сброс поворота в 0°');
            renderPool();
            renderActiveBookSlots();
            scheduleAutoSave();

            reloadStudioCropper(newCroppedBase, () => {
              fitStudioImageToContainer(false);
              cropperInstance.clear();
              cropperInstance.setDragMode('move');
              updateStudioModeUI('move');
              updateRotaryDialUI(0);
              applyStudioFilterPreview();
              updateZoomBadge();
              updateCropResolution();
              updateStudioHistoryUI();
              showToast('🔄 Угол сброшен в 0.0°');
            }, 'cropped');
          });
        }).catch(() => {});
        return;
      }

      animateStudioRotation(0, 240, () => {
        if (!currentEditingPhoto) return;
        currentEditingPhoto.rotation = 0;
        if (cropperInstance && cropperInstance.cropped) {
          const savedRel = syncCropFrameToPhoto();
          zoomStudioToCropBox(savedRel);
          recordStudioStep('Сброс поворота в 0°');
          markStudioChanged('Сброс поворота в 0°', true);
        } else {
          updateCurrentPhotoPreviewFromStudio(() => {
            recordStudioStep('Сброс поворота в 0°');
            markStudioChanged('Сброс поворота в 0°', true);
          });
        }
        showToast('🔄 Угол плавно сброшен в 0.0°');
      });
    }

    const resetFineRotation = resetStudioRotation;

    let dialRafId = null;

    function handleDialDrag(deg) {
      const roundedDeg = Math.round(deg * 10) / 10;
      studioCurrentRotation = roundedDeg;

      if (roundedDeg >= 300 || roundedDeg <= 65) {
        studioBaseCardinal = 0;
      } else if (roundedDeg > 65 && roundedDeg <= 155) {
        studioBaseCardinal = 90;
      } else if (roundedDeg > 155 && roundedDeg <= 245) {
        studioBaseCardinal = 180;
      } else {
        studioBaseCardinal = 270;
      }

      if (dialRafId) cancelAnimationFrame(dialRafId);
      dialRafId = requestAnimationFrame(() => {
        setStudioRotation(studioCurrentRotation, false, false);
      });

      markStudioChanged('Поворот', false);
    }

    let isDraggingDial = false;
    let dragStartPointerAngle = 0;
    let dragStartDialAngle = 0;

    function initRotaryDial() {
      const container = document.getElementById('rotaryDialContainer');
      if (!container || container._dialInitialized) return;
      container._dialInitialized = true;

      function getAngleFromPointer(e) {
        const rect = container.getBoundingClientRect();
        const centerX = rect.left + rect.width / 2;
        const centerY = rect.top + rect.height / 2;
        const clientX = (e.touches && e.touches.length > 0) ? e.touches[0].clientX : e.clientX;
        const clientY = (e.touches && e.touches.length > 0) ? e.touches[0].clientY : e.clientY;

        const dx = clientX - centerX;
        const dy = clientY - centerY;

        let deg = (Math.atan2(dy, dx) * 180 / Math.PI) + 90;
        if (deg < 0) deg += 360;
        return deg;
      }

      function onPointerDown(e) {
        if (rotationAnimationId) {
          cancelAnimationFrame(rotationAnimationId);
          rotationAnimationId = null;
        }

        // Если фото сейчас открыто в режиме чистого среза ('cropped') —
        // плавно переходим на полный исходник с рамкой, чтобы выравнивать горизонт прямо внутри рамки!
        if (studioLoadedSourceType === 'cropped' && currentEditingPhoto) {
          switchToFullSourceForCrop();
        }

        e.preventDefault();
        isDraggingDial = true;
        container.classList.remove('cursor-grab');
        container.classList.add('cursor-grabbing');

        dragStartPointerAngle = getAngleFromPointer(e);
        dragStartDialAngle = studioCurrentRotation;

        const onMove = (ev) => {
          if (!isDraggingDial) return;
          ev.preventDefault();
          const currentPointerAngle = getAngleFromPointer(ev);
          let delta = currentPointerAngle - dragStartPointerAngle;
          while (delta > 180) delta -= 360;
          while (delta < -180) delta += 360;

          let targetDeg = ((dragStartDialAngle + delta) % 360 + 360) % 360;
          handleDialDrag(targetDeg);
        };

        const onUp = () => {
          if (!isDraggingDial) return;
          isDraggingDial = false;
          container.classList.remove('cursor-grabbing');
          container.classList.add('cursor-grab');
          window.removeEventListener('mousemove', onMove);
          window.removeEventListener('mouseup', onUp);
          window.removeEventListener('touchmove', onMove);
          window.removeEventListener('touchend', onUp);

          if (currentEditingPhoto) {
            currentEditingPhoto.rotation = studioCurrentRotation;
          }
          const rotLabel = 'Поворот ' + studioCurrentRotation.toFixed(1) + '°';
          if (cropperInstance && cropperInstance.cropped && studioLoadedSourceType === 'full') {
            const savedRel = syncCropFrameToPhoto();
            zoomStudioToCropBox(savedRel);
            recordStudioStep(rotLabel);
            markStudioChanged(rotLabel, true);
          } else {
            updateCurrentPhotoPreviewFromStudio(() => {
              recordStudioStep(rotLabel);
              markStudioChanged(rotLabel, true);
            });
          }
        };

        window.addEventListener('mousemove', onMove);
        window.addEventListener('mouseup', onUp);
        window.addEventListener('touchmove', onMove, { passive: false });
        window.addEventListener('touchend', onUp);
      }

      container.addEventListener('mousedown', onPointerDown);
      container.addEventListener('touchstart', onPointerDown, { passive: false });
    }

    function setCropRatio(mode) {
      if (!cropperInstance) return;
      const normalizedMode = (!mode || mode === 'free' || mode === 'none') ? 'none' : mode;
      cropRatio = normalizedMode;
      updateCropRatioButtons(normalizedMode);

      const applyRatio = () => {
        if (!cropperInstance.cropped) {
          restoreCropFrameOnFullSource(false);
        }

        // Свободная пропорция: снимаем ограничение БЕЗ сброса и сдвига текущей рамки!
        if (normalizedMode === 'none') {
          applyCropAspectRatioToInstance('none');
          isFreeCroppingActive = true;
          cropperInstance.setDragMode('move');
          updateStudioModeUI('crop');
          syncCropFrameToPhoto();
          recordStudioStep('Пропорция: Свободно');
          updateCropResolution();
          updateCropResetButtonVisibility();
          markStudioChanged();
          return;
        }

        // Пропорции 3:4 (портрет Ozon) или 1:1 — подгоняем ВОКРУГ ЦЕНТРА текущей рамки!
        const targetRatio = (normalizedMode === '3:4') ? (3 / 4) : 1;
        const cData = cropperInstance.getCanvasData();
        const curCb = cropperInstance.getCropBoxData();

        applyCropAspectRatioToInstance(normalizedMode);

        if (cData && cData.width > 0 && cData.height > 0 && curCb && curCb.width > 15 && curCb.height > 15) {
          const cx = curCb.left + curCb.width / 2;
          const cy = curCb.top + curCb.height / 2;

          let newW, newH;
          if (curCb.width / curCb.height > targetRatio) {
            newH = curCb.height;
            newW = newH * targetRatio;
          } else {
            newW = curCb.width;
            newH = newW / targetRatio;
          }

          if (newW > cData.width) {
            newW = cData.width;
            newH = newW / targetRatio;
          }
          if (newH > cData.height) {
            newH = cData.height;
            newW = newH * targetRatio;
          }

          const newLeft = Math.max(cData.left, Math.min(cData.left + cData.width - newW, cx - newW / 2));
          const newTop = Math.max(cData.top, Math.min(cData.top + cData.height - newH, cy - newH / 2));

          isProgrammaticCropBoxUpdate = true;
          cropperInstance.setCropBoxData({
            left: newLeft,
            top: newTop,
            width: newW,
            height: newH
          });
          isProgrammaticCropBoxUpdate = false;
        }

        isFreeCroppingActive = true;
        cropperInstance.setDragMode('move');
        updateStudioModeUI('crop');
        const savedRel = syncCropFrameToPhoto();
        zoomStudioToCropBox(savedRel);
        recordStudioStep(`Пропорция ${normalizedMode}`);
        updateCropResolution();
        updateCropResetButtonVisibility();
        markStudioChanged();
      };

      if (studioLoadedSourceType !== 'full') {
        switchToFullSourceForCrop(applyRatio);
        return;
      }

      applyRatio();
    }

    function applyMarginCrop(percent) {
      if (!cropperInstance) return;

      const applyMargin = () => {
        if (!cropperInstance.cropped) {
          restoreCropFrameOnFullSource(false);
        }
        const cb = cropperInstance.getCropBoxData();
        const p = (percent / 100.0) / 2.0;
        const marginX = cb.width * p;
        const marginY = cb.height * p;

        isProgrammaticCropBoxUpdate = true;
        cropperInstance.setCropBoxData({
          left: cb.left + marginX,
          top: cb.top + marginY,
          width: Math.max(40, cb.width - marginX * 2),
          height: Math.max(40, cb.height - marginY * 2)
        });
        isProgrammaticCropBoxUpdate = false;

        const savedRel = syncCropFrameToPhoto();
        zoomStudioToCropBox(savedRel);
        recordStudioStep(`Поля -${percent}%`);
        updateCropResolution();
        updateCropResetButtonVisibility();
        markStudioChanged();
        showToast(`✂️ Поля сужены на ${percent}%`);
      };

      if (studioLoadedSourceType !== 'full') {
        switchToFullSourceForCrop(applyMargin);
        return;
      }

      applyMargin();
    }

    function resetCropBox() {
      if (!cropperInstance) return;
      const doReset = () => {
        if (!cropperInstance.cropped) {
          cropperInstance.crop();
        }
        isFreeCroppingActive = true;
        cropperInstance.setDragMode('move');
        fitStudioImageToContainer(true);
        const savedRel = syncCropFrameToPhoto();
        zoomStudioToCropBox(savedRel);
        recordStudioStep('Рамка на весь кадр');
        updateStudioModeUI('crop');
        markStudioChanged();
      };
      if (studioLoadedSourceType !== 'full') {
        switchToFullSourceForCrop(doReset);
      } else {
        doReset();
      }
    }

    function showStudioOriginal() {
      const badge = document.getElementById('studioOriginalBadge');
      if (badge) badge.classList.remove('hidden');
      const imgs = document.querySelectorAll('#studioCropperContainer img');
      imgs.forEach(img => { img.style.filter = 'none'; });
    }

    function hideStudioOriginal() {
      const badge = document.getElementById('studioOriginalBadge');
      if (badge) badge.classList.add('hidden');
      applyStudioFilterPreview();
    }

    window.addEventListener('resize', () => {
      handleStudioContainerResize();
    });

    function applyPixelFiltersToCanvas(canvas, state) {
      const W = state.whiten || 0;
      const B = state.brightness || 0;
      const C = state.contrast || 0;
      const S = state.saturation || 0;

      if (W === 0 && B === 0 && C === 0 && S === 0) return;

      const ctx = canvas.getContext('2d');
      const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const d = imgData.data;
      const len = d.length;

      const whitenT = 255.0 - (W / 100.0) * 75.0;
      const whitenRange = 255.0 - whitenT;
      const brightAdd = B * 2.55;
      const contrastFactor = C !== 0 ? (259.0 * (C + 255.0)) / (255.0 * (259.0 - C)) : 1.0;
      const satFactor = S !== 0 ? 1.0 + (S / 50.0) : 1.0;

      for (let i = 0; i < len; i += 4) {
        let r = d[i];
        let g = d[i + 1];
        let b = d[i + 2];

        // 1. Отбеливание фона
        if (W > 0) {
          const lum = 0.299 * r + 0.587 * g + 0.114 * b;
          if (lum > whitenT) {
            const tNorm = (lum - whitenT) / whitenRange;
            const factor = (tNorm > 0.75) ? 1.0 : (tNorm * (1.5 - 0.5 * tNorm));
            r += (255.0 - r) * factor;
            g += (255.0 - g) * factor;
            b += (255.0 - b) * factor;
          }
        }

        // 2. Яркость
        if (B !== 0) {
          r += brightAdd;
          g += brightAdd;
          b += brightAdd;
        }

        // 3. Контрастность
        if (C !== 0) {
          r = contrastFactor * (r - 128) + 128;
          g = contrastFactor * (g - 128) + 128;
          b = contrastFactor * (b - 128) + 128;
        }

        // 4. Насыщенность
        if (S !== 0) {
          const gray = 0.299 * r + 0.587 * g + 0.114 * b;
          r = gray + satFactor * (r - gray);
          g = gray + satFactor * (g - gray);
          b = gray + satFactor * (b - gray);
        }

        d[i] = r > 255 ? 255 : (r < 0 ? 0 : r);
        d[i + 1] = g > 255 ? 255 : (g < 0 ? 0 : g);
        d[i + 2] = b > 255 ? 255 : (b < 0 ? 0 : b);
      }

      ctx.putImageData(imgData, 0, 0);
    }

    function saveStudioChanges(onDoneCallback, keepModalOpen = false) {
      if (!currentEditingPhoto || !cropperInstance) return;

      const btn = document.getElementById('btnStudioSave');
      const origHtml = btn ? btn.innerHTML : '';
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span class="animate-spin inline-block mr-1">⏳</span> <span>Сохранение...</span>`;
      }

      try {
        const isCroppedActive = Boolean(currentEditingPhoto.isCropped || (cropperInstance && cropperInstance.cropped));

        if (isCroppedActive && studioLoadedSourceType === 'full' && cropperInstance && cropperInstance.cropped) {
          syncCropFrameToPhoto();
        }

        const croppedCanvas = cropperInstance.getCroppedCanvas({
          fillColor: '#ffffff',
          imageSmoothingEnabled: true,
          imageSmoothingQuality: 'high'
        });

        if (!croppedCanvas) {
          throw new Error('Не удалось получить изображение из редактора');
        }

        let cleanCroppedUrl = null;
        if (isCroppedActive) {
          cleanCroppedUrl = croppedCanvas.toDataURL('image/jpeg', 0.94);
        }

        applyPixelFiltersToCanvas(croppedCanvas, studioState);

        const dataUrl = croppedCanvas.toDataURL('image/jpeg', 0.92);
        const base64Data = dataUrl.split(',')[1];

        currentEditingPhoto.preview = dataUrl;
        currentEditingPhoto.data = base64Data;
        currentEditingPhoto.mime = 'image/jpeg';
        currentEditingPhoto.isCropped = isCroppedActive;
        currentEditingPhoto.croppedBase = isCroppedActive ? cleanCroppedUrl : null;
        currentEditingPhoto.whiten = studioState.whiten;
        currentEditingPhoto.brightness = studioState.brightness;
        currentEditingPhoto.contrast = studioState.contrast;
        currentEditingPhoto.saturation = studioState.saturation;
        currentEditingPhoto.rotation = studioCurrentRotation;
        currentEditingPhoto.isProcessed = Boolean(
          isCroppedActive ||
          studioState.whiten > 0 ||
          studioState.brightness !== 0 ||
          studioState.contrast !== 0 ||
          studioState.saturation !== 0 ||
          studioCurrentRotation !== 0 ||
          currentEditingPhoto.isAiProcessed
        );

        hasUnsavedStudioChanges = false;
        isFreeCroppingActive = false;
        updateAiBatchBtnState();

        const savedPhotoId = currentEditingPhoto.id;
        const assignedSlot = currentEditingPhoto.assignedSlot;
        currentEditingPhoto.is_s3_uploaded = false;
        currentEditingPhoto.s3_url = null;
        currentEditingPhoto.url = null;

        // Синхронизация неразрушающих параметров с SQLite-реестром ассетов
        if (savedPhotoId && (savedPhotoId.startsWith('ast_') || savedPhotoId.startsWith('photo_'))) {
          try {
            fetch('/api/assets/transform', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({
                asset_id: savedPhotoId,
                crop: currentEditingPhoto.cropRelative || currentEditingPhoto.crop_relative || null,
                rotation: studioCurrentRotation,
                filters: {
                  whiten: studioState.whiten,
                  brightness: studioState.brightness,
                  contrast: studioState.contrast,
                  saturation: studioState.saturation
                }
              })
            }).catch(e => console.warn('Ошибка синхронизации ассета:', e));
          } catch(e) {}
        }

        if (!keepModalOpen) {
          isStudioOpen = false;
          if (cropperInstance) {
            cropperInstance.destroy();
            cropperInstance = null;
          }
          const modal = document.getElementById('photoStudioModal');
          if (modal) modal.classList.add('hidden');
          currentEditingPhoto = null;
        }

        renderPool();
        renderActiveBookSlots();
        scheduleAutoSave();

        // Шаг 3 спецификации: планируем упреждающую выгрузку отредактированного кадра в S3
        if (assignedSlot && typeof scheduleProactiveS3Upload === 'function') {
          scheduleProactiveS3Upload(savedPhotoId, assignedSlot, 2500);
        }

        if (!keepModalOpen) {
          showToast(isCroppedActive ? '💾 Обрезка и настройки фото сохранены!' : '💾 Фото сохранено в полном кадре!');
        }

        if (typeof onDoneCallback === 'function') {
          onDoneCallback();
        }
      } catch (err) {
        console.error('Ошибка сохранения фото:', err);
        alert('Ошибка при сохранении фото: ' + err.message);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.innerHTML = origHtml;
        }
      }
    }

    async function processPhotoOffscreen(photo) {
      if (!photo.cameraOriginal) photo.cameraOriginal = photo.rawOriginal || photo.preview;
      if (!photo.rawOriginal) photo.rawOriginal = photo.cameraOriginal;
      const fullSource = getPhotoFullSource(photo);
      const rot = ((photo.rotation || 0) % 360 + 360) % 360;
      const rel = (photo.isCropped && (photo.cropRelative || photo.aiCropRelative))
        ? (photo.cropRelative || photo.aiCropRelative)
        : null;

      let baseUrl = fullSource;
      if (rel || Math.abs(rot) > 0.05) {
        baseUrl = await renderCroppedFromFullSourceAsync(fullSource, rot, rel);
        if (photo.isCropped && rel) {
          photo.croppedBase = baseUrl;
        }
      }

      const filters = {
        whiten: photo.whiten || 0,
        brightness: photo.brightness || 0,
        contrast: photo.contrast || 0,
        saturation: photo.saturation || 0
      };
      const filteredUrl = await applyFiltersToImageAsync(baseUrl, filters);
      photo.preview = filteredUrl;
      photo.data = filteredUrl.includes(',') ? filteredUrl.split(',')[1] : filteredUrl;
      photo.mime = 'image/jpeg';
      photo.isProcessed = isPhotoProcessed(photo);
      return photo;
    }

    function revertPhotoToOriginal(photoId, e) {
      if (e) e.stopPropagation();
      const photo = findPhotoById(photoId);
      if (!photo) return;

      const origSrc = photo.cameraOriginal || photo.rawOriginal;
      if (!origSrc) {
        showToast('ℹ️ Фото уже в исходном состоянии');
        return;
      }

      photo.preview = origSrc;
      photo.data = origSrc.includes(',') ? origSrc.split(',')[1] : origSrc;
      photo.rawOriginal = origSrc;
      photo.croppedBase = null;
      photo.aiWhiteOriginal = null;
      photo.aiCropRelative = null;
      photo.cropRelative = null;
      photo.cropBoxOnOriginal = null;
      photo.isCropped = false;
      photo.isAutoCropped = false;
      photo.isAiProcessed = false;
      photo.isProcessed = false;
      photo.whiten = 0;
      photo.brightness = 0;
      photo.contrast = 0;
      photo.saturation = 0;
      photo.rotation = 0;
      photo.history = [];
      initPhotoHistory(photo);

      renderPool();
      renderActiveBookSlots();
      scheduleAutoSave();
      showToast('↩️ Исходное фото с камеры восстановлено (1 шаг)');
    }

    function revertSelectedPhoto() {
      if (!selectedPoolPhotoId) return;
      revertPhotoToOriginal(selectedPoolPhotoId);
    }

    function revertStudioToCameraOriginal() {
      if (!currentEditingPhoto) return;

      const origSrc = currentEditingPhoto.cameraOriginal || currentEditingPhoto.rawOriginal;
      if (!origSrc) {
        alert('Исходный снимок не найден.');
        return;
      }

      currentEditingPhoto.croppedBase = null;
      currentEditingPhoto.aiWhiteOriginal = null;
      currentEditingPhoto.aiCropRelative = null;
      currentEditingPhoto.cropRelative = null;
      currentEditingPhoto.cropBoxOnOriginal = null;
      currentEditingPhoto.isCropped = false;
      currentEditingPhoto.isAutoCropped = false;
      currentEditingPhoto.whiten = 0;
      currentEditingPhoto.brightness = 0;
      currentEditingPhoto.contrast = 0;
      currentEditingPhoto.saturation = 0;
      currentEditingPhoto.rotation = 0;
      currentEditingPhoto.isProcessed = false;
      currentEditingPhoto.isAiProcessed = false;
      currentEditingPhoto.preview = origSrc;
      currentEditingPhoto.data = origSrc.includes(',') ? origSrc.split(',')[1] : origSrc;

      studioState.whiten = 0;
      studioState.brightness = 0;
      studioState.contrast = 0;
      studioState.saturation = 0;
      studioCurrentRotation = 0;
      studioBaseCardinal = 0;
      studioBaseRotation = 0;
      studioFineRotation = 0;
      studioCropBoxOnOriginal = null;
      isFreeCroppingActive = false;
      updateRotaryDialUI(0);

      document.getElementById('sliderWhiten').value = 0;
      document.getElementById('sliderBrightness').value = 0;
      document.getElementById('sliderContrast').value = 0;
      document.getElementById('sliderSaturation').value = 0;
      updateStudioBadges();

      cropRatio = 'none';
      preCropImageSrc = null;
      hasUnsavedCrop = false;
      updateCropRatioButtons('free');
      resetCropStateUI();

      recordStudioStep('Сброс к снимку с камеры');

      reloadStudioCropper(origSrc, () => {
        fitStudioImageToContainer(false);
        cropperInstance.clear();
        cropperInstance.setDragMode('move');
        updateStudioModeUI('move');
        updateZoomBadge();
        updateCropResolution();
        applyStudioFilterPreview();
        updateCropResetButtonVisibility();
        updateStudioHistoryUI();
      }, 'full');

      applyStudioFilterPreview();
      markStudioChanged();
      renderPool();
      renderActiveBookSlots();
      scheduleAutoSave();
      showToast('↩️ Исходное фото с камеры восстановлено в редакторе');
    }

    async function quickRotatePhoto(photoId, deg, e) {
      if (e) e.stopPropagation();
      const photo = findPhotoById(photoId);
      const photoBook = photo && photo.assignedBookId ? (window.booksSession || []).find(b => b.id === photo.assignedBookId) : (typeof window.getActiveBook === 'function' ? window.getActiveBook() : null);
      const isPhotoBusy = Boolean(photo && (photo.isProcessing || photo.isAiProcessing));
      if (!photo || isPhotoBusy) return;

      initPhotoHistory(photo);
      const direction = deg > 0 ? 1 : -1;
      photo.rotation = (((photo.rotation || 0) + deg) % 360 + 360) % 360;
      if (photo.isCropped && (photo.cropRelative || photo.aiCropRelative)) {
        const transformed = transformCropRelativeBy90(photo.cropRelative || photo.aiCropRelative, direction);
        photo.cropRelative = transformed;
        photo.aiCropRelative = transformed;
      }

      await processPhotoOffscreen(photo);

      if (!Array.isArray(photo.history)) photo.history = [];
      photo.history.push({
        label: `Поворот на ${photo.rotation}°`,
        timestamp: Date.now(),
        preview: photo.preview,
        data: photo.data,
        croppedBase: photo.croppedBase || null,
        rawOriginal: photo.rawOriginal,
        cameraOriginal: photo.cameraOriginal,
        aiWhiteOriginal: photo.aiWhiteOriginal || null,
        isCropped: Boolean(photo.isCropped),
        isAiProcessed: Boolean(photo.isAiProcessed),
        inCropMode: false,
        hasCropBox: Boolean(photo.isCropped),
        cropBoxOnOriginal: photo.cropBoxOnOriginal || null,
        cropRelative: photo.cropRelative ? { ...photo.cropRelative } : null,
        cropRatio: 'none',
        whiten: photo.whiten || 0,
        brightness: photo.brightness || 0,
        contrast: photo.contrast || 0,
        saturation: photo.saturation || 0,
        rotation: photo.rotation,
        cardinal: Math.round(photo.rotation / 90) * 90 % 360
      });
      photo.historyIndex = photo.history.length - 1;

      renderPool();
      renderActiveBookSlots();
      scheduleAutoSave();
    }

    async function quickWhitenPhoto(photoId, e) {
      if (e) e.stopPropagation();
      const photo = findPhotoById(photoId);
      const photoBook = photo && photo.assignedBookId ? (window.booksSession || []).find(b => b.id === photo.assignedBookId) : (typeof window.getActiveBook === 'function' ? window.getActiveBook() : null);
      const isPhotoBusy = Boolean(photo && (photo.isProcessing || photo.isAiProcessing));
      if (!photo || isPhotoBusy) return;
      photo.isProcessing = true;
      renderPool();
      renderActiveBookSlots();
      try {
        if (!photo.cameraOriginal) photo.cameraOriginal = photo.rawOriginal || photo.preview;
        if (!photo.rawOriginal) photo.rawOriginal = photo.cameraOriginal;
        initPhotoHistory(photo);
        photo.whiten = 85;
        photo.brightness = 4;
        photo.contrast = 8;
        await processPhotoOffscreen(photo);
        photo.isProcessed = true;
        showToast(`⚪ Фон кадра "${photo.name}" быстро отбелен!`);
      } catch (err) {
        showToast(`❌ Ошибка отбеливания: ${err.message}`, 3000);
      } finally {
        photo.isProcessing = false;
        renderPool();
        renderActiveBookSlots();
        scheduleAutoSave();
      }
    }

    async function runStudioAiProcess() {
      if (!currentEditingPhoto || !cropperInstance) return;
      const btn = document.getElementById('btnStudioAiProcess');
      const origHtml = btn ? btn.innerHTML : '';
      if (btn) {
        btn.disabled = true;
        btn.classList.add('opacity-75');
        btn.innerHTML = `<span class="animate-spin inline-block mr-1">⏳</span> <span>ИИ вырезает...</span>`;
      }

      try {
        // Если сейчас в режиме среза с активной рамкой — фиксируем её координаты перед ИИ-обработкой
        if (isFreeCroppingActive && studioLoadedSourceType === 'full' && cropperInstance.cropped) {
          syncCropFrameToPhoto();
        }

        // Берем полный исходник для чистого удаления фона нейросетью rembg
        const fullSource = getPhotoFullSource(currentEditingPhoto);
        const sourceToProcess = fullSource || currentEditingPhoto.cameraOriginal || currentEditingPhoto.rawOriginal || currentEditingPhoto.preview;

        const res = await fetch('/api/ai_process_photo', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            image: sourceToProcess,
            force_rembg: true,
            role: currentEditingPhoto.assignedSlot || 'cover_front'
          })
        });
        const data = await res.json();
        if (!data.success || !data.image) {
          throw new Error(data.error || 'Ошибка ИИ-обработки');
        }

        if (!currentEditingPhoto.cameraOriginal) {
          currentEditingPhoto.cameraOriginal = currentEditingPhoto.rawOriginal || currentEditingPhoto.preview;
        }

        // Сохраняем новый чистый белый оригинал (неразрушающая база)
        currentEditingPhoto.aiWhiteOriginal = data.image;
        currentEditingPhoto.isProcessed = true;
        currentEditingPhoto.isAiProcessed = true;
        currentEditingPhoto.rotation = studioCurrentRotation;

        // Сохраняем пользовательскую рамку; если своей еще не было — используем авто-рамку контура книги от ИИ
        let effectiveCropRel = currentEditingPhoto.cropRelative || currentEditingPhoto.aiCropRelative || data.crop_relative;
        if (effectiveCropRel) {
          currentEditingPhoto.cropRelative = { ...effectiveCropRel };
          currentEditingPhoto.aiCropRelative = { ...effectiveCropRel };
        }

        // Нарезаем новое белое изображение с учетом И угла поворота, И рамки!
        let newCroppedBase = null;
        if (effectiveCropRel) {
          try {
            newCroppedBase = await renderCroppedFromFullSourceAsync(data.image, studioCurrentRotation, effectiveCropRel);
          } catch (e) {
            console.warn('Не удалось нарезать кадр с белым фоном:', e);
          }
        }

        if (newCroppedBase) {
          currentEditingPhoto.croppedBase = newCroppedBase;
          currentEditingPhoto.isCropped = true;
        }

        // Применяем активные фильтры студии к новому кадру
        const previewBase = currentEditingPhoto.croppedBase
          || (Math.abs(studioCurrentRotation) > 0.05
            ? await renderCroppedFromFullSourceAsync(data.image, studioCurrentRotation, null)
            : data.image);
        const filteredDataUrl = await applyFiltersToImageAsync(previewBase, studioState);
        currentEditingPhoto.preview = filteredDataUrl;
        currentEditingPhoto.data = filteredDataUrl.includes(',') ? filteredDataUrl.split(',')[1] : filteredDataUrl;
        currentEditingPhoto.mime = 'image/jpeg';
        currentEditingPhoto.is_s3_uploaded = false;
        currentEditingPhoto.s3_url = null;
        currentEditingPhoto.url = null;

        isFreeCroppingActive = false;

        // Записываем шаг в историю (для гарантированного отката по кнопке «Шаг назад»)
        recordStudioStep('ИИ белый фон (rembg)');

        // Отображаем НОВОЕ изображение в редакторе, зафиксированным в рамке в режиме перемещения
        const displaySrc = currentEditingPhoto.croppedBase || data.image;
        const displayType = currentEditingPhoto.croppedBase ? 'cropped' : 'full';
        reloadStudioCropper(displaySrc, () => {
          if (displayType === 'full' && studioCurrentRotation !== 0) {
            cropperInstance.rotateTo(studioCurrentRotation);
          }
          fitStudioImageToContainer(false);
          cropperInstance.clear();
          cropperInstance.setDragMode('move');
          updateStudioModeUI('move');
          updateRotaryDialUI(studioCurrentRotation);
          updateZoomBadge();
          updateCropResolution();
          applyStudioFilterPreview();
          updateCropResetButtonVisibility();
          updateStudioHistoryUI();
        }, displayType);

        markStudioChanged('ИИ белый фон (rembg)');
        renderPool();
        renderActiveBookSlots();
        scheduleAutoSave();
        showToast('✨ ИИ аккуратно удалил фон книги на чистый белый!');
      } catch (err) {
        alert('Ошибка ИИ-обработки: ' + err.message);
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.classList.remove('opacity-75');
          btn.innerHTML = origHtml;
        }
      }
    }
