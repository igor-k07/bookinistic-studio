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
    let cropRatio = 'free';
    let isFreeCroppingActive = false;
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
      if (isBookAiRecognizing) {
        btn.disabled = true;
        btn.classList.add('opacity-50', 'cursor-not-allowed', 'grayscale');
        btn.title = 'Идет распознавание книги через Gemini...';
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
          preview: baseSrc,
          data: photo.data,
          croppedBase: photo.croppedBase || null,
          rawOriginal: photo.rawOriginal || baseSrc,
          cameraOriginal: photo.cameraOriginal || baseSrc,
          isCropped: Boolean(photo.isCropped),
          isAiProcessed: Boolean(photo.isAiProcessed),
          hasCropBox: Boolean(photo.isCropped),
          cropBoxOnOriginal: null,
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
        hasCropBox: Boolean(cropperInstance && cropperInstance.cropped),
        cropBoxOnOriginal: studioCropBoxOnOriginal ? { ...studioCropBoxOnOriginal } : null,
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
             Math.abs(s1.rotation - s2.rotation) < 0.1 &&
             s1.isCropped === s2.isCropped &&
             s1.isAiProcessed === s2.isAiProcessed &&
             s1.hasCropBox === s2.hasCropBox &&
             s1.croppedBase === s2.croppedBase &&
             s1.cropRatio === s2.cropRatio;
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

      currentEditingPhoto.history.push(newState);
      if (currentEditingPhoto.history.length > 30) {
        currentEditingPhoto.history.shift();
      }
      currentEditingPhoto.historyIndex = currentEditingPhoto.history.length - 1;

      updateStudioHistoryUI();
      markStudioChanged(label, false);
    }

    const pushPhotoHistory = (photo, label) => recordStudioStep(label);

    function commitStudioSliderStep(label) {
      recordStudioStep(label);
    }

    function applyStudioState(targetState, callback) {
      if (!currentEditingPhoto || !targetState) return;

      // 1. Обновляем параметры студии
      studioState.whiten = targetState.whiten;
      studioState.brightness = targetState.brightness;
      studioState.contrast = targetState.contrast;
      studioState.saturation = targetState.saturation;
      studioCurrentRotation = targetState.rotation;
      studioBaseCardinal = targetState.cardinal;
      studioBaseRotation = targetState.rotation;
      studioFineRotation = 0;
      cropRatio = targetState.cropRatio || 'none';
      studioCropBoxOnOriginal = targetState.cropBoxOnOriginal ? { ...targetState.cropBoxOnOriginal } : null;

      // 2. Обновляем контролы UI
      const slW = document.getElementById('sliderWhiten'); if (slW) slW.value = studioState.whiten;
      const slB = document.getElementById('sliderBrightness'); if (slB) slB.value = studioState.brightness;
      const slC = document.getElementById('sliderContrast'); if (slC) slC.value = studioState.contrast;
      const slS = document.getElementById('sliderSaturation'); if (slS) slS.value = studioState.saturation;
      updateStudioBadges();
      updateCropRatioButtons(cropRatio === 'none' ? null : cropRatio);

      // 3. Обновляем поля объекта photo
      currentEditingPhoto.preview = targetState.preview;
      currentEditingPhoto.data = targetState.data;
      currentEditingPhoto.croppedBase = targetState.croppedBase;
      currentEditingPhoto.isCropped = targetState.isCropped;
      currentEditingPhoto.isAiProcessed = targetState.isAiProcessed;
      currentEditingPhoto.whiten = targetState.whiten;
      currentEditingPhoto.brightness = targetState.brightness;
      currentEditingPhoto.contrast = targetState.contrast;
      currentEditingPhoto.saturation = targetState.saturation;
      currentEditingPhoto.rotation = targetState.rotation;
      currentEditingPhoto.isProcessed = Boolean(targetState.isCropped || targetState.whiten > 0 || targetState.isAiProcessed);

      // 4. Проверяем, изменился ли сам файл изображения (например, ИИ вырезка фона)
      const currentImgSrc = (cropperInstance && cropperInstance.image) ? (cropperInstance.image.src || '') : '';
      if (targetState.aiWhiteOriginal !== undefined) {
        currentEditingPhoto.aiWhiteOriginal = targetState.aiWhiteOriginal;
      }
      const targetSrc = (targetState.isCropped && targetState.croppedBase)
        ? targetState.croppedBase
        : (currentEditingPhoto.aiWhiteOriginal || currentEditingPhoto.cameraOriginal || targetState.preview);
      const isDifferentImageSrc = !cropperInstance || (currentImgSrc && !currentImgSrc.endsWith(targetSrc) && currentImgSrc !== targetSrc);

      if (isDifferentImageSrc) {
        // Перезагружаем Cropper только если физически сменился источник пикселей (rembg)
        reloadStudioCropper(targetSrc, () => {
          setStudioRotation(studioCurrentRotation, true, false);
          if (targetState.hasCropBox && studioCropBoxOnOriginal) {
            cropperInstance.crop();
            updateCropBoxForCurrentRotation();
          } else {
            cropperInstance.clear();
          }
          applyStudioFilterPreview();
          updateCropResetButtonVisibility();
          updateCropResolution();
          updateZoomBadge();
          renderPool();
          renderActiveBookSlots();
          scheduleAutoSave();
          if (typeof callback === 'function') callback();
        });
      } else {
        // Мгновенное применение БЕЗ перезагрузки Cropper
        setStudioRotation(studioCurrentRotation, false, false);
        if (targetState.hasCropBox && studioCropBoxOnOriginal) {
          if (!cropperInstance.cropped) cropperInstance.crop();
          updateCropBoxForCurrentRotation();
        } else {
          if (cropperInstance.cropped) cropperInstance.clear();
        }
        applyStudioFilterPreview();
        updateCropResetButtonVisibility();
        updateCropResolution();
        updateZoomBadge();
        renderPool();
        renderActiveBookSlots();
        scheduleAutoSave();
        if (typeof callback === 'function') callback();
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

      if (hasUnsavedStudioChanges) {
        saveStudioChanges(() => {
          openPhotoStudio(targetPhoto.id);
          showToast(`📸 Фото #${targetIdx + 1}: ${targetPhoto.name}`);
        }, true);
      } else {
        openPhotoStudio(targetPhoto.id);
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
      setStudioRotation(studioCurrentRotation, false, false);
      updateStudioBadges();

      cropRatio = 'none';
      isFreeCroppingActive = false;
      hasUnsavedCrop = false;
      studioCropBoxOnOriginal = null;
      preCropImageSrc = null;
      updateCropRatioButtons(null);
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

      const baseSource = (photo.isCropped && photo.croppedBase)
        ? photo.croppedBase
        : (photo.aiWhiteOriginal || photo.cameraOriginal || photo.rawOriginal || photo.preview);
      document.getElementById('photoStudioModal').classList.remove('hidden');

      reloadStudioCropper(baseSource, () => {
        if (studioCurrentRotation !== 0) {
          cropperInstance.rotateTo(studioCurrentRotation);
        }
        fitStudioImageToContainer(false);
        initStudioSmoothZoom();
        resetCropStateUI();

        // Если есть сохраненные относительные координаты контура книги, сразу выставляем рамку (только если фото еще НЕ обрезано)
        if (!photo.isCropped && photo.aiWhiteOriginal && photo.aiCropRelative) {
          try {
            const canvasData = cropperInstance.getCanvasData();
            const rel = photo.aiCropRelative;
            const cbLeft = canvasData.left + rel.x * canvasData.width;
            const cbTop = canvasData.top + rel.y * canvasData.height;
            const cbWidth = rel.w * canvasData.width;
            const cbHeight = rel.h * canvasData.height;
            cropperInstance.crop();
            isProgrammaticCropBoxUpdate = true;
            cropperInstance.setCropBoxData({
              left: cbLeft,
              top: cbTop,
              width: cbWidth,
              height: cbHeight
            });
            isProgrammaticCropBoxUpdate = false;
            captureCropBoxOnOriginal();
            zoomStudioToCropBox();
          } catch (err) {
            console.error('Ошибка выставления авто-рамки книги:', err);
          }
        }

        if (photo.isCropped) {
          updateCropResetButtonVisibility();
        }
        if (startMode === 'crop') {
          setStudioInteractionMode('crop');
        } else {
          setStudioInteractionMode('move');
        }
        updateCropResolution();
        updateZoomBadge();
        applyStudioFilterPreview();
        updateStudioPhotoNavUI();
        updateStudioHistoryUI();
      });
    }

    function reloadStudioCropper(sourceUrl, onReadyCallback) {
      if (cropperInstance) {
        cropperInstance.destroy();
        cropperInstance = null;
      }

      const imgEl = document.getElementById('studioCropperImage');
      if (!imgEl) return;
      imgEl.onload = null;

      imgEl.onload = () => {
        imgEl.onload = null;
        if (cropperInstance) {
          cropperInstance.destroy();
          cropperInstance = null;
        }

        cropperInstance = new Cropper(imgEl, {
          viewMode: 0,
          dragMode: 'move',
          autoCrop: false,
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
              setStudioInteractionMode('move');
              updateZoomBadge();
              updateCropResolution();
              applyStudioFilterPreview();
            }
          },
          crop(event) {
            updateCropResolution();
          },
          cropmove() {
            markStudioChanged();
          },
          cropend() {
            if (!isProgrammaticCropBoxUpdate && cropperInstance && cropperInstance.cropped) {
              const cb = cropperInstance.getCropBoxData();
              if (cb && cb.width > 25 && cb.height > 25) {
                zoomStudioToCropBox();
              } else {
                captureCropBoxOnOriginal();
              }
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

      imgEl.src = sourceUrl;
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
      if (!cropperInstance) return;

      pushPhotoHistory(currentEditingPhoto, 'Сброс рамки');

      if (currentEditingPhoto && (currentEditingPhoto.croppedBase || currentEditingPhoto.isCropped)) {
        const origSrc = currentEditingPhoto.aiWhiteOriginal || currentEditingPhoto.cameraOriginal || currentEditingPhoto.rawOriginal || currentEditingPhoto.preview;
        currentEditingPhoto.croppedBase = null;
        currentEditingPhoto.isCropped = false;
        currentEditingPhoto.isAutoCropped = false;
        currentEditingPhoto.aiCropRelative = null;
        currentEditingPhoto.preview = origSrc;
        currentEditingPhoto.data = origSrc.includes(',') ? origSrc.split(',')[1] : origSrc;
        preCropImageSrc = null;
        studioCropBoxOnOriginal = null;
        reloadStudioCropper(origSrc, () => {
          if (studioCurrentRotation !== 0) {
            cropperInstance.rotateTo(studioCurrentRotation);
          }
          fitStudioImageToContainer(false);
          setStudioInteractionMode('move');
          updateCropRatioButtons(null);
          updateCropResolution();
          updateZoomBadge();
          applyStudioFilterPreview();
          updateCropResetButtonVisibility();
          updateStudioHistoryUI();
          renderPool();
          renderActiveBookSlots();
          scheduleAutoSave();
          markStudioChanged('Сброс рамки', true);
        });
      } else {
        if (currentEditingPhoto) {
          currentEditingPhoto.isCropped = false;
          currentEditingPhoto.isAutoCropped = false;
          currentEditingPhoto.aiCropRelative = null;
        }
        studioCropBoxOnOriginal = null;
        cropperInstance.clear();
        setStudioInteractionMode('move');
        updateCropRatioButtons(null);
        updateCropResolution();
        updateZoomBadge();
        updateCropResetButtonVisibility();
        updateStudioHistoryUI();
        markStudioChanged('Сброс рамки', true);
      }
      showToast('↩️ Рамка снята: выбран исходный полный кадр');
    }

    const cancelCropMode = resetCropToOriginal;

    function zoomStudioToCropBox() {
      if (!cropperInstance || !cropperInstance.cropped) return;

      const container = cropperInstance.getContainerData();
      const canvas = cropperInstance.getCanvasData();
      const cb = cropperInstance.getCropBoxData();

      if (!cb || !cb.width || !cb.height || cb.width < 20 || cb.height < 20) return;
      if (!container || !container.width || !container.height) return;
      if (!canvas || !canvas.width || !canvas.height) return;

      // Безопасные отступы от краев рабочей зоны редактора:
      // padBottom = 48px гарантирует, что ни рамка, ни нижний край фото не перекроются панелью инструментов
      const padX = 40;
      const padTop = 28;
      const padBottom = 48;

      const availW = Math.max(100, container.width - padX * 2);
      const availH = Math.max(100, container.height - padTop - padBottom);

      // Зона обрезки масштабируется так, чтобы занимать 72% безопасной области просмотра по центру.
      // Оставшиеся ~14% пространства с каждой стороны позволяют пользователю видеть внешние края фотографии,
      // сохраняя контекст вокруг выделения.
      const CROP_VIEW_FRACTION = 0.72;
      const targetCbW = availW * CROP_VIEW_FRACTION;
      const targetCbH = availH * CROP_VIEW_FRACTION;

      const scale = Math.min(targetCbW / cb.width, targetCbH / cb.height);
      if (!isFinite(scale) || scale <= 0) return;

      const clampedScale = Math.max(0.25, Math.min(scale, 4.0));

      const newCanvasW = canvas.width * clampedScale;
      const newCanvasH = canvas.height * clampedScale;
      const newCbW = cb.width * clampedScale;
      const newCbH = cb.height * clampedScale;

      // Центрируем зону обрезки строго по центру безопасной области
      const centerX = container.width / 2;
      const centerY = padTop + availH / 2;

      const newCbLeft = centerX - newCbW / 2;
      const newCbTop = centerY - newCbH / 2;

      // Смещение рамки относительно начала холста
      const offsetInCanvasX = cb.left - canvas.left;
      const offsetInCanvasY = cb.top - canvas.top;

      const newCanvasLeft = newCbLeft - offsetInCanvasX * clampedScale;
      const newCanvasTop = newCbTop - offsetInCanvasY * clampedScale;

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

      captureCropBoxOnOriginal();
      updateCropResolution();
      updateZoomBadge();
      updateCropResetButtonVisibility();
      markStudioChanged('Приближение к зоне обрезки');
    }

    function commitStudioCrop() {
      if (!cropperInstance || !currentEditingPhoto) return;

      if (cropperInstance.cropped) {
        const croppedCanvas = cropperInstance.getCroppedCanvas({
          fillColor: '#ffffff',
          imageSmoothingEnabled: true,
          imageSmoothingQuality: 'high'
        });

        if (croppedCanvas) {
          pushPhotoHistory(currentEditingPhoto, 'Обрезка кадра');
          const cleanCroppedUrl = croppedCanvas.toDataURL('image/jpeg', 0.94);

          // Применяем текущие фильтры студии к превью для пула и слотов
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
          currentEditingPhoto.aiCropRelative = null;

          renderPool();
          renderActiveBookSlots();
          scheduleAutoSave();

          reloadStudioCropper(cleanCroppedUrl, () => {
            fitStudioImageToContainer(false);
            setStudioInteractionMode('move');
            updateZoomBadge();
            updateCropResolution();
            applyStudioFilterPreview();
            updateCropResetButtonVisibility();
            updateStudioHistoryUI();
            showToast('✂️ Картинка сохранена в области среза!');
          });
          return;
        }
      }

      setStudioInteractionMode('move');
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
      setStudioInteractionMode('move');
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

      currentEditingPhoto = null;
      hasUnsavedStudioChanges = false;
      isStudioOpen = false;
      updateAiBatchBtnState();
    }

    function updateStudioBadges() {
      document.getElementById('valWhiten').textContent = `${studioState.whiten}%`;
      document.getElementById('valBrightness').textContent = `${studioState.brightness > 0 ? '+' : ''}${studioState.brightness}%`;
      document.getElementById('valContrast').textContent = `${studioState.contrast > 0 ? '+' : ''}${studioState.contrast}%`;
      document.getElementById('valSaturation').textContent = `${studioState.saturation > 0 ? '+' : ''}${studioState.saturation}%`;
    }

    function updateCropRatioButtons(activeMode) {
      const pairs = [
        { key: 'free', btns: ['ratioBtn_free', 'ratioBtnSide_free'] },
        { key: '3:4',  btns: ['ratioBtn_34', 'ratioBtnSide_34'] },
        { key: '1:1',  btns: ['ratioBtn_11', 'ratioBtnSide_11'] }
      ];
      pairs.forEach(p => {
        const isActive = (p.key === activeMode);
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

    function setStudioInteractionMode(mode) {
      if (!cropperInstance) return;
      const btnMove = document.getElementById('btnModeMove');
      const btnCrop = document.getElementById('btnModeCrop');
      const btnCropText = document.getElementById('btnModeCropText');
      const qr = document.getElementById('cropRatioQuickRow');
      const crs = document.getElementById('studioCropRightSection');
      const hint = document.getElementById('studioCropHint');

      if (mode === 'crop') {
        isFreeCroppingActive = true;
        cropperInstance.setDragMode('crop');

        // Не навязываем рамку на весь экран: оставляем свободный курсор прицел, чтобы оператор выделил область сам
        if (!cropperInstance.cropped) {
          cropperInstance.clear();
        }

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
          hint.innerHTML = '✂️ <b>Режим среза активен</b>: выделите нужную область мышью (прицел). Повторный клик или [C] сохранит изображение в области среза.';
        }
      } else {
        isFreeCroppingActive = false;
        cropperInstance.setDragMode('move');

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
        setStudioInteractionMode('crop');
        showToast('✂️ Режим среза: выделите область мышью на фото');
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
    function setupStudioResizeObserver() {
      const container = document.getElementById('studioCropperContainer');
      if (!container || studioResizeObserver) return;
      if (typeof ResizeObserver === 'undefined') return;

      studioResizeObserver = new ResizeObserver((entries) => {
        if (!isStudioOpen || !cropperInstance) return;
        for (const entry of entries) {
          if (entry.contentRect.width > 50 && entry.contentRect.height > 50) {
            cropperInstance.resize();
            if (cropperInstance.cropped) {
              zoomStudioToCropBox();
            } else {
              fitStudioImageToContainer(false);
            }
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
      if (cropperInstance.cropped) {
        zoomStudioToCropBox();
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

      // Учитываем текущий угол поворота холста для точного расчета соотношения сторон
      const rad = ((studioCurrentRotation || 0) * Math.PI) / 180;
      const rotW = Math.abs(nw * Math.cos(rad)) + Math.abs(nh * Math.sin(rad));
      const rotH = Math.abs(nw * Math.sin(rad)) + Math.abs(nh * Math.cos(rad));
      const aspect = (rotW > 0 && rotH > 0) ? (rotW / rotH) : (cw / ch);

      // Оставляем комфортные безопасные отступы вокруг фото (по бокам, сверху и снизу),
      // чтобы изображение всегда оставалось полностью видимым с запасом свободного места
      // и гарантированно не перекрывалось нижней панелью инструментов
      const padX = 36;
      const padTop = 24;
      const padBottom = 44;
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
        // Кадрирование не включено: центрируем и масштабируем только холст
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

      // Устанавливаем холст точно по рассчитанным пропорциям, чтобы он на 100% помещался в окно
      cropperInstance.setCanvasData({
        left: fitLeft,
        top: fitTop,
        width: fitW,
        height: fitH
      });

      // Сохраняем и восстанавливаем рамку по относительным координатам
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
        captureCropBoxOnOriginal();
      } else if (resetCropBox) {
        isProgrammaticCropBoxUpdate = true;
        cropperInstance.setCropBoxData({
          left: fitLeft,
          top: fitTop,
          width: fitW,
          height: fitH
        });
        isProgrammaticCropBoxUpdate = false;
        captureCropBoxOnOriginal();
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
      pushPhotoHistory(currentEditingPhoto, 'Пресет: ' + presetName);
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
      markStudioChanged('Пресет: ' + presetName);
    }

    function setStudioRotation(deg, fitToContainer = false, pushHistory = false) {
      let normalized = ((deg % 360) + 360) % 360;
      normalized = Math.round(normalized * 10) / 10;
      studioCurrentRotation = normalized;
      studioBaseRotation = normalized;

      if (pushHistory && currentEditingPhoto) {
        pushPhotoHistory(currentEditingPhoto, `Поворот на ${studioCurrentRotation}°`);
      }

      // Поворачиваем стрелку и шкалу ротора диска
      const rotor = document.getElementById('rotaryDialRotor');
      if (rotor) {
        rotor.style.transform = `rotate(${studioCurrentRotation}deg)`;
      }

      // Центр диска с текстом держим прямо (контр-вращение)
      const centerDisplay = document.getElementById('rotaryCenterDisplay');
      if (centerDisplay) {
        centerDisplay.style.transform = `rotate(-${studioCurrentRotation}deg)`;
      }

      // Отображаем угол: от -180° до +180° (для удобства оператора)
      const angleText = document.getElementById('rotaryAngleText');
      if (angleText) {
        const displayAngle = studioCurrentRotation > 180
          ? (studioCurrentRotation - 360).toFixed(1)
          : studioCurrentRotation.toFixed(1);
        const sign = parseFloat(displayAngle) > 0 ? '+' : '';
        angleText.textContent = `${sign}${displayAngle}°`;
      }

      // Поворачиваем холст Cropper.js на GPU
      if (cropperInstance) {
        if (cropperInstance.cropped && !studioCropBoxOnOriginal) {
          captureCropBoxOnOriginal();
        }

        cropperInstance.rotateTo(studioCurrentRotation);

        if (cropperInstance.cropped && studioCropBoxOnOriginal && !fitToContainer) {
          updateCropBoxForCurrentRotation();
        }

        if (fitToContainer) {
          fitStudioImageToContainer(false);
        }
      }
    }

    let rotationAnimationId = null;

    function animateStudioRotation(targetAngle, durationMs = 280, onComplete) {
      if (rotationAnimationId) {
        cancelAnimationFrame(rotationAnimationId);
        rotationAnimationId = null;
      }

      if (cropperInstance && cropperInstance.cropped && !studioCropBoxOnOriginal) {
        captureCropBoxOnOriginal();
      }

      const startAngle = studioCurrentRotation;
      let diff = targetAngle - startAngle;
      while (diff > 180) diff -= 360;
      while (diff < -180) diff += 360;

      if (Math.abs(diff) < 0.2) {
        setStudioRotation(targetAngle, true, false);
        if (cropperInstance && cropperInstance.cropped) {
          captureCropBoxOnOriginal();
        }
        if (typeof onComplete === 'function') onComplete();
        return;
      }

      const startTime = performance.now();

      function step(now) {
        const elapsed = now - startTime;
        const progress = Math.min(1, elapsed / durationMs);
        // Мягкая кривая замедления (cubic ease-out)
        const easeOut = 1 - Math.pow(1 - progress, 3);
        const currentDeg = startAngle + diff * easeOut;

        setStudioRotation(currentDeg, false, false);

        if (progress < 1) {
          rotationAnimationId = requestAnimationFrame(step);
        } else {
          rotationAnimationId = null;
          setStudioRotation(targetAngle, true, false);
          if (cropperInstance && cropperInstance.cropped) {
            captureCropBoxOnOriginal();
          }
          if (typeof onComplete === 'function') onComplete();
        }
      }

      rotationAnimationId = requestAnimationFrame(step);
    }

    function rotateStudioStep(direction) {
      let relCrop = null;
      if (cropperInstance && cropperInstance.cropped) {
        const c = cropperInstance.getCanvasData();
        const b = cropperInstance.getCropBoxData();
        if (c && b && c.width > 0 && c.height > 0) {
          const rx = (b.left - c.left) / c.width;
          const ry = (b.top - c.top) / c.height;
          const rw = b.width / c.width;
          const rh = b.height / c.height;
          if (direction > 0) { // Вправо (+90°)
            relCrop = {
              x: Math.max(0, 1 - ry - rh),
              y: Math.max(0, rx),
              w: Math.min(1, rh),
              h: Math.min(1, rw)
            };
          } else { // Влево (-90°)
            relCrop = {
              x: Math.max(0, ry),
              y: Math.max(0, 1 - rx - rw),
              w: Math.min(1, rh),
              h: Math.min(1, rw)
            };
          }
        }
      }

      // direction: +1 (Вправо / по часовой) или -1 (Влево / против часовой)
      let newCardinal;
      if (direction > 0) {
        newCardinal = (studioBaseCardinal + 90) % 360;
      } else {
        newCardinal = (studioBaseCardinal - 90 + 360) % 360;
      }
      studioBaseCardinal = newCardinal;
      pushPhotoHistory(currentEditingPhoto, `Поворот на ${newCardinal}°`);

      // Плавно анимируем вращение до новой кардинальной стороны
      animateStudioRotation(newCardinal, 280, () => {
        if (relCrop && cropperInstance && cropperInstance.cropped) {
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
            captureCropBoxOnOriginal();
            updateCropResolution();
          }
        }
        markStudioChanged(`Поворот на ${newCardinal}°`, true);
      });
    }

    const rotateStudio = (deg) => rotateStudioStep(deg > 0 ? 1 : -1);

    function resetStudioRotation() {
      if (cropperInstance && cropperInstance.cropped && !studioCropBoxOnOriginal) {
        captureCropBoxOnOriginal();
      }
      studioBaseCardinal = 0;
      pushPhotoHistory(currentEditingPhoto, 'Сброс поворота в 0°');
      animateStudioRotation(0, 250, () => {
        markStudioChanged('Сброс поворота в 0°', true);
        showToast('🔄 Угол плавно сброшен в 0.0°');
      });
    }

    const resetFineRotation = resetStudioRotation;

    let dialRafId = null;

    function handleDialDrag(deg) {
      const roundedDeg = Math.round(deg * 10) / 10;
      studioCurrentRotation = roundedDeg;

      // Обновляем базовый квадрант вокруг текущей ориентации:
      // Сектор [300°..360°] и [0°..65°] считает базой 0°
      // Сектор (65°..155°] считает базой 90°
      // Сектор (155°..245°] считает базой 180°
      // Сектор (245°..300°) считает базой 270°
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
        // Если шла плавная анимация от кнопки, останавливаем её
        if (rotationAnimationId) {
          cancelAnimationFrame(rotationAnimationId);
          rotationAnimationId = null;
        }

        if (cropperInstance && cropperInstance.cropped && !studioCropBoxOnOriginal) {
          captureCropBoxOnOriginal();
        }

        e.preventDefault();
        isDraggingDial = true;
        container.classList.remove('cursor-grab');
        container.classList.add('cursor-grabbing');

        // Фиксируем относительный угол старта — НЕТ РЕЗКОГО СКАЧКА ПРИ НАЖАТИИ!
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
          if (cropperInstance && cropperInstance.cropped) {
            captureCropBoxOnOriginal();
          }
          markStudioChanged('Поворот ' + studioCurrentRotation.toFixed(1) + '°', true);
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
      cropRatio = mode;
      updateCropRatioButtons(mode);

      const normDeg = ((studioCurrentRotation % 360) + 360) % 360;
      const nearestCardinal = Math.round(normDeg / 90) * 90 % 360;
      const isPerp = (nearestCardinal === 90 || nearestCardinal === 270);

      if (mode === '3:4') {
        cropperInstance.setAspectRatio(isPerp ? 4 / 3 : 3 / 4);
      } else if (mode === '1:1') {
        cropperInstance.setAspectRatio(1);
      } else {
        cropperInstance.setAspectRatio(NaN);
      }

      if (!cropperInstance.cropped) {
        cropperInstance.crop();
      }

      const cData = cropperInstance.getCanvasData();
      if (cData && cData.width && cData.height) {
        let cbW, cbH;
        const targetRatio = (mode === '3:4') ? (isPerp ? 4 / 3 : 3 / 4) : (mode === '1:1' ? 1 : null);
        if (targetRatio) {
          if (cData.width / cData.height > targetRatio) {
            cbH = cData.height * 0.90;
            cbW = cbH * targetRatio;
          } else {
            cbW = cData.width * 0.90;
            cbH = cbW / targetRatio;
          }
        } else {
          cbW = cData.width * 0.90;
          cbH = cData.height * 0.90;
        }
        isProgrammaticCropBoxUpdate = true;
        cropperInstance.setCropBoxData({
          left: cData.left + (cData.width - cbW) / 2,
          top: cData.top + (cData.height - cbH) / 2,
          width: cbW,
          height: cbH
        });
        isProgrammaticCropBoxUpdate = false;
      }

      setStudioInteractionMode('crop');
      captureCropBoxOnOriginal();
      zoomStudioToCropBox();
      updateCropResolution();
      updateCropResetButtonVisibility();
      markStudioChanged();
    }

    function applyMarginCrop(percent) {
      if (!cropperInstance) return;
      if (!cropperInstance.cropped) {
        cropperInstance.crop();
      }
      const cb = cropperInstance.getCropBoxData();
      const p = (percent / 100.0) / 2.0;
      const marginX = cb.width * p;
      const marginY = cb.height * p;

      isProgrammaticCropBoxUpdate = true;
      cropperInstance.setCropBoxData({
        left: cb.left + marginX,
        top: cb.top + marginY,
        width: Math.max(50, cb.width - marginX * 2),
        height: Math.max(50, cb.height - marginY * 2)
      });
      isProgrammaticCropBoxUpdate = false;

      captureCropBoxOnOriginal();
      zoomStudioToCropBox();
      updateCropResolution();
      updateCropResetButtonVisibility();
      markStudioChanged();
      showToast(`✂️ Поля сужены на ${percent}%`);
    }

    function resetCropBox() {
      if (!cropperInstance) return;
      if (!cropperInstance.cropped) {
        cropperInstance.crop();
        cropperInstance.setDragMode('crop');
      }
      fitStudioImageToContainer(true);
      captureCropBoxOnOriginal();
      markStudioChanged();
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
      if (isStudioOpen && cropperInstance) {
        cropperInstance.resize();
        if (cropperInstance.cropped) {
          zoomStudioToCropBox();
        } else {
          fitStudioImageToContainer(false);
        }
      }
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
        if (isCroppedActive) {
          currentEditingPhoto.aiCropRelative = null;
        }
        currentEditingPhoto.whiten = studioState.whiten;
        currentEditingPhoto.brightness = studioState.brightness;
        currentEditingPhoto.contrast = studioState.contrast;
        currentEditingPhoto.saturation = studioState.saturation;
        currentEditingPhoto.rotation = isCroppedActive ? 0 : studioCurrentRotation;
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
        updateAiBatchBtnState();

        const savedPhotoId = currentEditingPhoto.id;
        const assignedSlot = currentEditingPhoto.assignedSlot;
        currentEditingPhoto.is_s3_uploaded = false;
        currentEditingPhoto.s3_url = null;

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

    function processPhotoOffscreen(photo) {
      return new Promise((resolve) => {
        if (!photo.cameraOriginal) photo.cameraOriginal = photo.rawOriginal || photo.preview;
        if (!photo.rawOriginal) photo.rawOriginal = photo.cameraOriginal;
        const baseSrc = (photo.isCropped && photo.croppedBase)
          ? photo.croppedBase
          : (photo.aiWhiteOriginal || photo.cameraOriginal || photo.rawOriginal || photo.preview);
        const img = new Image();
        img.onload = () => {
          const rot = (photo.rotation || 0) % 360;
          const swap = (rot === 90 || rot === 270);
          const origW = img.naturalWidth || img.width;
          const origH = img.naturalHeight || img.height;

          const canvas = document.createElement('canvas');
          canvas.width = swap ? origH : origW;
          canvas.height = swap ? origW : origH;
          const ctx = canvas.getContext('2d');

          ctx.translate(canvas.width / 2, canvas.height / 2);
          ctx.rotate((rot * Math.PI) / 180);
          ctx.drawImage(img, -origW / 2, -origH / 2);

          const W = photo.whiten || 0;
          const B = photo.brightness || 0;
          const C = photo.contrast || 0;
          const S = photo.saturation || 0;

          if (W !== 0 || B !== 0 || C !== 0 || S !== 0) {
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

              if (B !== 0) {
                r += brightAdd;
                g += brightAdd;
                b += brightAdd;
              }

              if (C !== 0) {
                r = contrastFactor * (r - 128) + 128;
                g = contrastFactor * (g - 128) + 128;
                b = contrastFactor * (b - 128) + 128;
              }

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

          const dataUrl = canvas.toDataURL('image/jpeg', 0.90);
          photo.preview = dataUrl;
          photo.data = dataUrl.split(',')[1];
          photo.mime = 'image/jpeg';
          photo.isProcessed = isPhotoProcessed(photo);
          resolve(photo);
        };
        img.src = baseSrc;
      });
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
      photo.isCropped = false;
      photo.isAutoCropped = false;
      photo.isAiProcessed = false;
      photo.isProcessed = false;
      photo.whiten = 0;
      photo.brightness = 0;
      photo.contrast = 0;
      photo.saturation = 0;
      photo.rotation = 0;
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
      studioBaseCardinal = 0;
      setStudioRotation(0, false, false);

      document.getElementById('sliderWhiten').value = 0;
      document.getElementById('sliderBrightness').value = 0;
      document.getElementById('sliderContrast').value = 0;
      document.getElementById('sliderSaturation').value = 0;
      updateStudioBadges();

      cropRatio = 'none';
      preCropImageSrc = null;
      hasUnsavedCrop = false;
      updateCropRatioButtons(null);
      resetCropStateUI();

      recordStudioStep('Сброс к снимку с камеры');

      reloadStudioCropper(origSrc, () => {
        fitStudioImageToContainer(false);
        setStudioInteractionMode('move');
        updateZoomBadge();
        updateCropResolution();
        applyStudioFilterPreview();
        updateCropResetButtonVisibility();
        updateStudioHistoryUI();
      });

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
      if (!photo || photo.isProcessing || photo.isAiProcessing || isBookAiRecognizing) return;
      photo.rotation = (((photo.rotation || 0) + deg) % 360 + 360) % 360;
      await processPhotoOffscreen(photo);
      renderPool();
      renderActiveBookSlots();
      scheduleAutoSave();
    }

    async function quickWhitenPhoto(photoId, e) {
      if (e) e.stopPropagation();
      const photo = findPhotoById(photoId);
      if (!photo || photo.isProcessing || photo.isAiProcessing || isBookAiRecognizing) return;
      photo.isProcessing = true;
      renderPool();
      renderActiveBookSlots();
      try {
        if (!photo.cameraOriginal) photo.cameraOriginal = photo.rawOriginal || photo.preview;
        if (!photo.rawOriginal) photo.rawOriginal = photo.cameraOriginal;
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
        const tempCanvas = cropperInstance.getCroppedCanvas({
          fillColor: '#ffffff',
          imageSmoothingQuality: 'high'
        });
        const baseSource = tempCanvas ? tempCanvas.toDataURL('image/jpeg', 0.90) : (currentEditingPhoto.croppedBase || currentEditingPhoto.cameraOriginal || currentEditingPhoto.rawOriginal || currentEditingPhoto.preview);

        const res = await fetch('/api/ai_process_photo', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image: baseSource })
        });
        const data = await res.json();
        if (!data.success || !data.image) {
          throw new Error(data.error || 'Ошибка ИИ-обработки');
        }

        if (!currentEditingPhoto.cameraOriginal) {
          currentEditingPhoto.cameraOriginal = currentEditingPhoto.rawOriginal || currentEditingPhoto.preview;
        }
        currentEditingPhoto.aiWhiteOriginal = data.image;
        currentEditingPhoto.croppedBase = null;
        currentEditingPhoto.isCropped = false;
        currentEditingPhoto.preview = data.image;
        currentEditingPhoto.data = (typeof data.image === 'string' && data.image.includes(',')) ? data.image.split(',')[1] : data.image;
        currentEditingPhoto.aiCropRelative = data.crop_relative || null;
        currentEditingPhoto.whiten = 0;
        currentEditingPhoto.isProcessed = true;
        currentEditingPhoto.isAiProcessed = true;

        studioState.whiten = 0;
        const whitenSlider = document.getElementById('sliderWhiten');
        if (whitenSlider) whitenSlider.value = 0;
        updateStudioBadges();
        applyStudioFilterPreview();

        studioBaseCardinal = 0;
        setStudioRotation(0, false, false);

        cropRatio = 'none';
        updateCropRatioButtons(null);
        resetCropStateUI();

        pushPhotoHistory(currentEditingPhoto, 'ИИ белый фон (rembg)');

        reloadStudioCropper(data.image, () => {
          fitStudioImageToContainer(false);
          setStudioInteractionMode('move');
          if (data.crop_relative) {
            try {
              const canvasData = cropperInstance.getCanvasData();
              const rel = data.crop_relative;
              cropperInstance.crop();
              isProgrammaticCropBoxUpdate = true;
              cropperInstance.setCropBoxData({
                left: canvasData.left + rel.x * canvasData.width,
                top: canvasData.top + rel.y * canvasData.height,
                width: rel.w * canvasData.width,
                height: rel.h * canvasData.height
              });
              isProgrammaticCropBoxUpdate = false;
              captureCropBoxOnOriginal();
              zoomStudioToCropBox();
            } catch (err) {}
          }
          updateZoomBadge();
          updateCropResolution();
          updateCropResetButtonVisibility();
          updateStudioHistoryUI();
        });
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
