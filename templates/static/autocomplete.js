/**
 * autocomplete.js: Нечувствительное к регистру автодополнение полей книги (авторы, издательства, серии Ozon).
 */

async function loadCatalogReferences() {
  try {
    const resp = await fetch('/api/references');
    const data = await resp.json();
    if (data.success && data.references) {
      window.CATALOG_REFERENCES = data.references;
      initCustomAutocomplete();
    }
  } catch (e) {
    console.warn('Не удалось загрузить справочники каталога:', e);
  }
}

var currentAutocompleteInput = null;
var currentAutocompleteCategory = null;
var currentAutocompleteMatches = [];
var activeAutocompleteIndex = -1;

function cleanPublisherName(val) {
  if (!val || typeof val !== 'string') return '';
  let s = val.trim();
  // Очистка юридических префиксов издательства и кавычек по спецификации Ozon
  s = s.replace(/^(?:издательство|изд-во|изд\.?|ид|ооо|зао|оао|ип|издательская\s+группа|издательский\s+дом)\s+/i, '');
  s = s.replace(/\s+(?:издательство|изд-во|изд\.?|ид)$/i, '');
  s = s.replace(/^["'«»“„”`]+|["'«»“„”`]+$/g, '').trim();
  if (/^(?:издательство|изд-во|изд\.?)$/i.test(s)) return '';
  return s;
}
window.cleanPublisherName = cleanPublisherName;

function highlightMatch(text, query) {
  if (!query) return escapeHtml(text);
  const lowerText = text.toLowerCase();
  const lowerQ = query.toLowerCase();
  const idx = lowerText.indexOf(lowerQ);
  if (idx === -1) return escapeHtml(text);
  const before = escapeHtml(text.substring(0, idx));
  const match = escapeHtml(text.substring(idx, idx + query.length));
  const after = escapeHtml(text.substring(idx + query.length));
  return `${before}<span class="text-amber-400 font-bold underline decoration-amber-400/50">${match}</span>${after}`;
}

function showCustomAutocomplete(inputEl, categoryKey) {
  const menu = document.getElementById('customAutocompleteMenu');
  if (!menu) return;

  const raw = (inputEl.value || '').trim();
  const rawLower = raw.toLowerCase();
  let list = (window.CATALOG_REFERENCES && window.CATALOG_REFERENCES[categoryKey]) || [];
  if (!list.length) {
    hideCustomAutocomplete();
    return;
  }

  const isAuthor = (categoryKey === 'authors' || inputEl.id === 'author' || inputEl.id === 'author_cover');
  const isPublisher = (categoryKey === 'publishers' || inputEl.id === 'publisher');

  if (isPublisher) {
    list = Array.from(new Set(list.map(cleanPublisherName).filter(Boolean)));
  }

  let matches = [];
  if (isAuthor) {
    // В справочнике Ozon официальный вариант при отсутствии автора — строго "не указан"
    const ozonDefault = 'не указан';
    if (!rawLower || 'не указан'.startsWith(rawLower) || rawLower.includes('не') || rawLower.includes('авт') || rawLower.includes('нет')) {
      matches.push(ozonDefault);
    }
  }

  if (!rawLower) {
    // Если поле пустое, показываем первые варианты (для автора 'не указан' уже в начале)
    const candidates = list.filter(item => item.toLowerCase() !== 'не указан' && item.toLowerCase() !== 'автор не указан');
    matches = matches.concat(candidates.slice(0, 15));
  } else {
    // 100% case-insensitive: сначала начинающиеся с запроса, затем содержащие запрос
    const starts = [];
    const contains = [];
    for (const item of list) {
      const itemLower = item.toLowerCase();
      if (itemLower === 'автор не указан') continue;
      if (itemLower === 'не указан' && matches.includes('не указан')) continue;
      if (itemLower.startsWith(rawLower)) {
        starts.push(item);
      } else if (itemLower.includes(rawLower) || itemLower.replace(/["'«»]/g, '').includes(rawLower.replace(/["'«»]/g, ''))) {
        contains.push(item);
      }
      if (starts.length + contains.length >= 35) break;
    }
    matches = matches.concat(starts).concat(contains).slice(0, 25);
  }

  if (!matches.length) {
    hideCustomAutocomplete();
    return;
  }

  currentAutocompleteInput = inputEl;
  currentAutocompleteCategory = categoryKey;
  currentAutocompleteMatches = matches;
  activeAutocompleteIndex = -1;

  menu.innerHTML = matches.map((item, idx) => {
    const isSpecialOzon = (item === 'не указан');
    const badgeText = isSpecialOzon ? 'по Ozon' : 'в базе';
    const badgeColor = isSpecialOzon ? 'text-emerald-400 bg-emerald-950/60 border border-emerald-500/30 px-1.5 py-0.5 rounded' : 'text-slate-500';
    return `
      <div class="autocomplete-item px-3 py-1.5 cursor-pointer text-slate-200 hover:bg-amber-500/20 hover:text-amber-300 font-medium transition flex items-center justify-between" data-index="${idx}" data-val="${escapeHtml(item)}">
        <span class="truncate ${isSpecialOzon ? 'text-emerald-300 font-bold' : ''}">${highlightMatch(item, raw)}</span>
        <span class="text-[9px] ${badgeColor} ml-2 shrink-0">${badgeText}</span>
      </div>
    `;
  }).join('');

  const rect = inputEl.getBoundingClientRect();
  menu.style.top = `${rect.bottom + 4}px`;
  menu.style.left = `${rect.left}px`;
  menu.style.width = `${Math.max(rect.width, 240)}px`;
  menu.classList.remove('hidden');
}

function selectAutocompleteItem(val) {
  if (currentAutocompleteInput && val) {
    let finalVal = val;
    if (currentAutocompleteCategory === 'publishers' || currentAutocompleteInput.id === 'publisher') {
      finalVal = cleanPublisherName(val);
    }
    currentAutocompleteInput.value = finalVal;
    currentAutocompleteInput.dispatchEvent(new Event('input', { bubbles: true }));
    currentAutocompleteInput.dispatchEvent(new Event('change', { bubbles: true }));
    currentAutocompleteInput.classList.add('field-updated');
    setTimeout(() => currentAutocompleteInput && currentAutocompleteInput.classList.remove('field-updated'), 800);

    if (currentAutocompleteCategory === 'publishers' || currentAutocompleteInput.id === 'publisher') {
      syncBrandWithPublisher(finalVal);
    }
  }
  hideCustomAutocomplete();
}

function hideCustomAutocomplete() {
  const menu = document.getElementById('customAutocompleteMenu');
  if (menu) menu.classList.add('hidden');
  currentAutocompleteInput = null;
  currentAutocompleteCategory = null;
  currentAutocompleteMatches = [];
  activeAutocompleteIndex = -1;
}

function updateAutocompleteHighlight() {
  const menu = document.getElementById('customAutocompleteMenu');
  if (!menu) return;
  const items = menu.querySelectorAll('.autocomplete-item');
  items.forEach((item, idx) => {
    if (idx === activeAutocompleteIndex) {
      item.classList.add('bg-amber-500/25', 'text-amber-300');
      item.scrollIntoView({ block: 'nearest' });
    } else {
      item.classList.remove('bg-amber-500/25', 'text-amber-300');
    }
  });
}

function initCustomAutocomplete() {
  const menu = document.getElementById('customAutocompleteMenu');
  if (menu && !menu._hasListeners) {
    menu._hasListeners = true;
    menu.addEventListener('mousedown', (e) => {
      e.preventDefault(); // prevent blur on input
      const item = e.target.closest('.autocomplete-item');
      if (item) {
        selectAutocompleteItem(item.getAttribute('data-val'));
      }
    });
  }

  document.addEventListener('pointerdown', (e) => {
    const m = document.getElementById('customAutocompleteMenu');
    if (!m || m.classList.contains('hidden')) return;
    if (!m.contains(e.target) && e.target !== currentAutocompleteInput) {
      hideCustomAutocomplete();
    }
  });

  window.addEventListener('scroll', hideCustomAutocomplete, true);
  window.addEventListener('resize', hideCustomAutocomplete);

  document.querySelectorAll('[data-autocomplete]').forEach(el => {
    if (el._hasAutoInit) return;
    el._hasAutoInit = true;
    const cat = el.getAttribute('data-autocomplete');

    if (el.id === 'publisher') {
      el.addEventListener('input', () => {
        clearTimeout(el._brandSyncTimer);
        el._brandSyncTimer = setTimeout(() => syncBrandWithPublisher(el.value), 300);
      });
    }

    el.addEventListener('focus', () => showCustomAutocomplete(el, cat));
    el.addEventListener('input', () => showCustomAutocomplete(el, cat));
    el.addEventListener('blur', () => {
      setTimeout(() => {
        snapToCanonical(el, cat);
        hideCustomAutocomplete();
      }, 150);
    });
    el.addEventListener('change', () => snapToCanonical(el, cat));

    el.addEventListener('keydown', (e) => {
      const m = document.getElementById('customAutocompleteMenu');
      if (!m || m.classList.contains('hidden')) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        activeAutocompleteIndex = (activeAutocompleteIndex + 1) % currentAutocompleteMatches.length;
        updateAutocompleteHighlight();
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        activeAutocompleteIndex = (activeAutocompleteIndex - 1 + currentAutocompleteMatches.length) % currentAutocompleteMatches.length;
        updateAutocompleteHighlight();
      } else if (e.key === 'Enter' || e.key === 'Tab') {
        if (activeAutocompleteIndex >= 0 && activeAutocompleteIndex < currentAutocompleteMatches.length) {
          e.preventDefault();
          selectAutocompleteItem(currentAutocompleteMatches[activeAutocompleteIndex]);
        }
      } else if (e.key === 'Escape') {
        hideCustomAutocomplete();
      }
    });
  });
}

// Нечувствительная к регистру сверка с эталонной базой
function snapToCanonical(inputEl, categoryKey) {
  if (!inputEl) return;
  const raw = (inputEl.value || '').trim();
  if (!raw) return;

  const rawLower = raw.toLowerCase();

  // 1. Для авторов: если автор не указан — строго официальное значение Ozon "не указан"
  if (categoryKey === 'authors' || inputEl.id === 'author' || inputEl.id === 'author_cover') {
    if (['автор не указан', 'нет автора', 'неизвестен', 'нет', 'отсутствует', 'без автора', 'не указан'].includes(rawLower)) {
      if (inputEl.value !== 'не указан') {
        inputEl.value = 'не указан';
        inputEl.classList.add('field-updated');
        setTimeout(() => inputEl.classList.remove('field-updated'), 800);
      }
    }
    return;
  }

  // 2. Для издательства: убираем слово "издательство", "изд-во", "ИД" и кавычки
  if (categoryKey === 'publishers' || inputEl.id === 'publisher') {
    const cleaned = cleanPublisherName(raw);
    if (cleaned && cleaned !== raw) {
      inputEl.value = cleaned;
      inputEl.classList.add('field-updated');
      setTimeout(() => inputEl.classList.remove('field-updated'), 800);
    }
    syncBrandWithPublisher(inputEl.value);
    return;
  }

  if (!window.CATALOG_REFERENCES) return;
  const list = window.CATALOG_REFERENCES[categoryKey] || [];

  // 3. Точное совпадение без учета регистра
  let matched = list.find(item => item.toLowerCase() === rawLower);

  // 4. Без кавычек ("Эксмо" <-> Эксмо <-> «эксмо»)
  if (!matched) {
    const cleanLower = rawLower.replace(/["'«»]/g, '').trim();
    matched = list.find(item => item.toLowerCase().replace(/["'«»]/g, '').trim() === cleanLower);
  }

  // 5. Для бренда: автоматическая нормализация "нет бренда"
  if (categoryKey === 'brands' && (rawLower === 'нет бренда' || rawLower === 'нет' || rawLower === 'без бренда' || rawLower === 'не указан')) {
    matched = 'Нет бренда';
  }

  if (matched && matched !== raw) {
    inputEl.value = matched;
    inputEl.classList.add('field-updated');
    setTimeout(() => inputEl.classList.remove('field-updated'), 800);
  }
}

// Функция сопоставления издательства с базой брендов Ozon:
// Пытается найти издательство в справочнике брендов Ozon.
// Если найдено — возвращает официальное имя бренда Ozon, иначе 'Нет бренда'.
function resolveBrandFromPublisher(publisherStr) {
  if (!publisherStr) return 'Нет бренда';
  const brandList = (window.CATALOG_REFERENCES && window.CATALOG_REFERENCES.brands) || [];
  if (!brandList.length) return 'Нет бренда';

  const clean = publisherStr.trim().replace(/^["'«»]+|["'«»]+$/g, '');
  if (!clean || clean.toLowerCase() === 'нет бренда' || clean.toLowerCase() === 'не указан') {
    return 'Нет бренда';
  }

  // Карта брендов: без кавычек и регистра
  const brandMap = {};
  for (const b of brandList) {
    if (b === 'Нет бренда') continue;
    const key = b.trim().replace(/^["'«»]+|["'«»]+$/g, '').toLowerCase();
    if (key) brandMap[key] = b;
  }

  // 1. Прямое совпадение
  const cleanLower = clean.toLowerCase();
  if (brandMap[cleanLower]) return brandMap[cleanLower];

  // 2. Очищенное от юридических префиксов (Издательство, Изд-во, ООО, и т.д.)
  const cand = clean.replace(/\b(?:издательство|изд-во|изд|ооо|зао|оао|ип|издательская\s+группа|издательский\s+дом)\b/gi, '')
                    .replace(/["'«».,]/g, ' ')
                    .trim()
                    .replace(/\s+/g, ' ');
  const candLower = cand.toLowerCase();
  if (candLower && brandMap[candLower]) return brandMap[candLower];

  return 'Нет бренда';
}

function syncBrandWithPublisher(pubVal) {
  const brandEl = document.getElementById('brand');
  if (!brandEl) return;
  const matchedBrand = resolveBrandFromPublisher(pubVal);
  brandEl.value = matchedBrand;
  const curBook = (typeof getActiveBook === 'function') ? getActiveBook() : null;
  if (curBook) {
    if (!curBook.formData) curBook.formData = {};
    curBook.formData.brand = matchedBrand;
  }
  brandEl.classList.add('field-updated');
  setTimeout(() => brandEl && brandEl.classList.remove('field-updated'), 800);
}
