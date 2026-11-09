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
  const list = (window.CATALOG_REFERENCES && window.CATALOG_REFERENCES[categoryKey]) || [];
  if (!list.length) {
    hideCustomAutocomplete();
    return;
  }

  let matches = [];
  if (!rawLower) {
    // Если поле пустое, показываем первые 15 популярных вариантов
    matches = list.slice(0, 15);
  } else {
    // 100% case-insensitive: сначала начинающиеся с запроса, затем содержащие запрос
    const starts = [];
    const contains = [];
    for (const item of list) {
      const itemLower = item.toLowerCase();
      if (itemLower.startsWith(rawLower)) {
        starts.push(item);
      } else if (itemLower.includes(rawLower) || itemLower.replace(/["'«»]/g, '').includes(rawLower.replace(/["'«»]/g, ''))) {
        contains.push(item);
      }
      if (starts.length + contains.length >= 35) break;
    }
    matches = starts.concat(contains).slice(0, 25);
  }

  if (!matches.length) {
    hideCustomAutocomplete();
    return;
  }

  currentAutocompleteInput = inputEl;
  currentAutocompleteCategory = categoryKey;
  currentAutocompleteMatches = matches;
  activeAutocompleteIndex = -1;

  menu.innerHTML = matches.map((item, idx) => `
    <div class="autocomplete-item px-3 py-1.5 cursor-pointer text-slate-200 hover:bg-amber-500/20 hover:text-amber-300 font-medium transition flex items-center justify-between" data-index="${idx}" data-val="${escapeHtml(item)}">
      <span class="truncate">${highlightMatch(item, raw)}</span>
      <span class="text-[9px] text-slate-500 ml-2 shrink-0">в базе</span>
    </div>
  `).join('');

  const rect = inputEl.getBoundingClientRect();
  menu.style.top = `${rect.bottom + 4}px`;
  menu.style.left = `${rect.left}px`;
  menu.style.width = `${Math.max(rect.width, 240)}px`;
  menu.classList.remove('hidden');
}

function selectAutocompleteItem(val) {
  if (currentAutocompleteInput && val) {
    currentAutocompleteInput.value = val;
    currentAutocompleteInput.dispatchEvent(new Event('input', { bubbles: true }));
    currentAutocompleteInput.dispatchEvent(new Event('change', { bubbles: true }));
    currentAutocompleteInput.classList.add('field-updated');
    setTimeout(() => currentAutocompleteInput && currentAutocompleteInput.classList.remove('field-updated'), 800);
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
  if (!inputEl || !window.CATALOG_REFERENCES) return;
  const raw = (inputEl.value || '').trim();
  if (!raw) return;
  const list = window.CATALOG_REFERENCES[categoryKey] || [];
  const rawLower = raw.toLowerCase();

  // 1. Точное совпадение без учета регистра
  let matched = list.find(item => item.toLowerCase() === rawLower);

  // 2. Без кавычек ("Эксмо" <-> Эксмо <-> «эксмо»)
  if (!matched) {
    const cleanLower = rawLower.replace(/["'«»]/g, '').trim();
    matched = list.find(item => item.toLowerCase().replace(/["'«»]/g, '').trim() === cleanLower);
  }

  // 3. Сопоставление авторов/персон по фамилии и инициалам
  if (!matched && (categoryKey === 'authors' || categoryKey === 'translators' || categoryKey === 'illustrators')) {
    const parts = raw.replace(/\./g, '. ').split(/\s+/).filter(Boolean);
    if (parts.length >= 1) {
      const surname = parts[0].toLowerCase();
      const cands = list.filter(item => item.toLowerCase().startsWith(surname + ' '));
      if (cands.length === 1) {
        matched = cands[0];
      } else if (cands.length > 1 && parts.length >= 2) {
        const firstInit = parts[1][0].toLowerCase();
        const subCands = cands.filter(c => {
          const cp = c.split(/\s+/);
          return cp.length >= 2 && cp[1][0].toLowerCase() === firstInit;
        });
        if (subCands.length === 1) {
          matched = subCands[0];
        }
      }
    }
  }

  // 4. Для бренда: автоматическая нормализация "нет бренда"
  if (categoryKey === 'brands' && (rawLower === 'нет бренда' || rawLower === 'нет' || rawLower === 'без бренда')) {
    matched = 'Нет бренда';
  }

  if (matched && matched !== raw) {
    inputEl.value = matched;
    inputEl.classList.add('field-updated');
    setTimeout(() => inputEl.classList.remove('field-updated'), 800);
  }
}
