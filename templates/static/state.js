/**
 * state.js: Глобальное состояние сессии, константы и базовые утилиты Bookinistic Studio.
 */

// Константы букинистики и Ozon
const ANNOTATION_WARNING = 'ВНИМАНИЕ! КНИГА НЕ НОВАЯ. Имеются определённые нюансы (повреждения) см. дополнительные фото.';

const OZON_GENRES = [
  "Проза", "История", "Фантастика", "Фэнтези", "Детектив", "Поэзия",
  "Научная и научно-популярная литература", "Искусство и культура",
  "Энциклопедия, справочник", "Словарь", "Биография", "Мемуары",
  "Публицистика", "Приключения", "Военное дело", "Политика и политология",
  "Право и юриспруденция", "Экономика и финансы", "Бизнес", "Психология",
  "Саморазвитие", "Религия", "Эзотерика и духовные практики", "Медицина",
  "Кулинария", "Хобби и творчество", "Дом и сад", "Спорт", "Красота и здоровье",
  "Информационные технологии", "Путешествия и туризм",
  "Античная литература", "Драматургия", "Любовный роман", "Триллер",
  "Мистика", "Ужасы", "Эпос и фольклор", "Басни", "Комикс", "Манга",
  "Дошкольное развитие детей", "Молодежная и подростковая литература (Young Adult)",
  "Графический роман", "Боевик", "Педагогика и логопедия"
];

/**
 * Нормализует жанр Ozon. Исключает несуществующий жанр 'Детская литература',
 * перенаправляя детские книги в реальные категории классификатора Ozon.
 */
function resolveOzonGenre(genre, title = '', annotation = '') {
  let g = (genre || '').trim();
  if (!g || g === 'Детская литература' || g.toLowerCase().includes('детск')) {
    const text = `${title} ${annotation}`.toLowerCase();
    if (text.match(/сказк|сказоч|былин|фольклор|миф|легенд|богатыр/)) {
      return 'Эпос и фольклор';
    }
    if (text.match(/стих|стихотвор|поэзи|поэм|рифм/)) {
      return 'Поэзия';
    }
    if (text.match(/басн/)) {
      return 'Басни';
    }
    if (text.match(/комикс|манга|графическ/)) {
      return 'Комикс';
    }
    if (text.match(/фантаст|космос|булычев|робот|пришелец|электроник/)) {
      return 'Фантастика';
    }
    if (text.match(/волшеб|маги|эльф|колдун|фея|фэнтези/)) {
      return 'Фэнтези';
    }
    if (text.match(/приключ|робинзон|индейц|пират|сыщик|следопыт|путешеств/)) {
      return 'Приключения';
    }
    if (text.match(/дошкольн|малыш|азбук|раскраск|пропис|для самых маленьких/)) {
      return 'Дошкольное развитие детей';
    }
    if (text.match(/подростк|young adult/)) {
      return 'Молодежная и подростковая литература (Young Adult)';
    }
    if (text.match(/энциклопед|почемучк|хочу все знать|справочник/)) {
      return 'Энциклопедия, справочник';
    }
    return 'Проза';
  }
  return g;
}

// Глобальное реактивное состояние сессии
var photoPool = []; // Массив всех фото: { id, name, mime, preview, cameraOriginal, ... }
var booksSession = [
  {
    id: 1,
    article: "DP-B-00001",
    title: "Книга #1",
    slots: {
      cover_front: null,
      cover_back: [],
      info_pages: [],
      illustrations: [],
      mantra_defects: []
    },
    formData: {
      article: "DP-B-00001",
      article_number: "00001",
      barcode: "2978470000012"
    }
  }
];
var activeBookId = 1;
var selectedPoolPhotoId = null;
var currentApiKey = (typeof localStorage !== 'undefined' && localStorage.getItem('gemini_api_key')) || '';
var currentMobileUrl = '';
var lastMobileEventId = 0;
var autoSaveTimer = null;
var currentTemplateMode = 'pre2011'; // 'pre2011' или 'post2011'
var isBookAiRecognizing = false; // Блокировка книги во время Gemini-анализа

var poolCardScale = 'large';
try {
  const savedScale = localStorage.getItem('bookinistic_pool_scale');
  if (savedScale && ['normal', 'large', 'xlarge'].includes(savedScale)) {
    poolCardScale = savedScale;
  }
} catch(e) {}

var draggedPhotoId = null;
var draggedSourceSlot = null;

// Базовые утилиты
function cleanAnnotationText(text) {
  if (!text) return '';
  let clean = String(text);
  while (clean.includes(ANNOTATION_WARNING)) {
    clean = clean.replace(ANNOTATION_WARNING, '').trim();
  }
  clean = clean.replace(/^ВНИМАНИЕ!\s*КНИГА\s*НЕ\s*НОВАЯ[^\n]*\n*/gi, '').trim();
  const markers = [
    '\\n\\nСохранность / Дефекты:', '\\n\\nСохранность:', '\\n\\nДефекты:',
    '\\nСохранность / Дефекты:', '\\nСохранность:', '\\nДефекты:',
    '\n\nСохранность / Дефекты:', '\n\nСохранность:', '\n\nДефекты:',
    '\nСохранность / Дефекты:', '\nСохранность:', '\nДефекты:'
  ];
  for (const m of markers) {
    if (clean.includes(m)) clean = clean.split(m)[0].trim();
  }
  while (clean.startsWith('\n')) clean = clean.substring(1).trim();
  return clean.trim();
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function findPhotoById(photoId) {
  if (!photoId) return null;
  let photo = photoPool.find(p => p.id === photoId);
  if (photo) return photo;
  for (const b of booksSession) {
    if (!b || !b.slots) continue;
    if (b.slots.cover_front && b.slots.cover_front.id === photoId) return b.slots.cover_front;
    for (const s of ['cover_back', 'info_pages', 'illustrations', 'mantra_defects']) {
      const list = Array.isArray(b.slots[s]) ? b.slots[s] : (b.slots[s] ? [b.slots[s]] : []);
      const found = list.find(p => p && p.id === photoId);
      if (found) return found;
    }
  }
  return null;
}

function getActiveBook() {
  return booksSession.find(b => b.id === activeBookId) || booksSession[0];
}

function isPhotoProcessed(photo) {
  if (!photo) return false;
  return Boolean(
    photo.isProcessed ||
    (photo.whiten !== undefined && photo.whiten > 0) ||
    (photo.brightness !== undefined && photo.brightness !== 0) ||
    (photo.contrast !== undefined && photo.contrast !== 0) ||
    (photo.saturation !== undefined && photo.saturation !== 0) ||
    (photo.rotation !== undefined && photo.rotation !== 0) ||
    photo.isCropped
  );
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
