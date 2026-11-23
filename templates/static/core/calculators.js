/**
 * calculators.js: Чистые функции расчета габаритов ГОСТ, упаковки, цен, штрихкодов EAN-13 и сохранности Ozon.
 * Инкапсулирует бизнес-формулы спецификации и устраняет дублирование кода в UI.
 * Работает как в браузере (window.BookCalculators), так и в среде тестирования Node.js.
 */

(function (global) {
  'use strict';

  const STORE_BARCODE_PREFIX = "297847"; // 29 (внутренний GS1) + 78 (СПб) + 47 (Другой Петербург)

  const SOVIET_FORMAT_MAP = {
    "70x100/16": [176, 235],
    "70x90/16": [170, 215],
    "70x108/16": [170, 260],
    "84x108/16": [205, 260],
    "60x90/16": [145, 215],
    "60x84/16": [145, 200],
    "84x108/32": [130, 200],
    "70x108/32": [130, 165],
    "70x100/32": [120, 165],
    "70x90/32": [110, 165],
    "60x90/32": [107, 140],
    "60x84/32": [100, 140],
  };

  /**
   * Распознает код типографского формата книги из строки (например "84x108/32").
   */
  function parseFormatCode(text) {
    if (!text) return null;
    const m = String(text).match(/(\d{2,3})\s*[xх*×]\s*(\d{2,3})\s*(?:(?:1\/|\/)\s*(\d{1,2}))/i);
    if (m) {
      const key = `${m[1]}x${m[2]}/${m[3]}`.toLowerCase();
      if (SOVIET_FORMAT_MAP[key]) {
        return { key, width: SOVIET_FORMAT_MAP[key][0], length: SOVIET_FORMAT_MAP[key][1] };
      }
    }
    const mDirect = String(text).match(/(\d{2,3})\s*[xх*×]\s*(\d{2,3})/i);
    if (mDirect) {
      let w = parseInt(mDirect[1], 10);
      let l = parseInt(mDirect[2], 10);
      if (w >= 80 && w <= 350 && l >= 100 && l <= 450) {
        if (w > l) { const tmp = w; w = l; l = tmp; }
        return { key: `${w}x${l}`, width: w, length: l };
      }
    }
    return null;
  }

  /**
   * Расчет габаритов и веса по ГОСТ (п. 5.2 спецификации).
   * Принцип независимости: ручные значения пользователя НЕ перезаписываются!
   */
  function calculateGostDimensions(formatCode, pages, coverType, existingDimensions = {}, allowOverwriteManual = false) {
    const hasManualW = existingDimensions.width_mm && parseInt(existingDimensions.width_mm, 10) > 0;
    const hasManualL = existingDimensions.length_mm && parseInt(existingDimensions.length_mm, 10) > 0;
    const hasManualH = existingDimensions.height_mm && parseInt(existingDimensions.height_mm, 10) > 0;
    const hasManualWeight = existingDimensions.weight_g && parseInt(existingDimensions.weight_g, 10) > 0;

    let width = 130;
    let length = 205;
    let fmtKey = '';

    const parsed = parseFormatCode(formatCode);
    if (parsed) {
      fmtKey = parsed.key;
      width = parsed.width;
      length = parsed.length;
    }

    const pagesInt = Math.max(0, parseInt(pages, 10) || 0);
    const isSoft = (coverType || '').toLowerCase().includes('мягк') || (coverType || '').toLowerCase().includes('обложка');
    const coverAdd = isSoft ? 4 : 6;
    let spine = Math.round(pagesInt * 0.048 + coverAdd);
    spine = pagesInt > 0 ? Math.max(4, Math.min(spine, 150)) : 15;

    let weight = 250;
    if (fmtKey === '70x100/16' || fmtKey === '70x90/16') {
      weight = Math.round(pagesInt * 0.95 + (isSoft ? 70 : 140));
    } else if (fmtKey === '60x90/16') {
      weight = Math.round(pagesInt * 0.70 + (isSoft ? 50 : 90));
    } else if (['70x108/32', '70x100/32', '60x90/32', '60x84/32'].includes(fmtKey)) {
      weight = Math.round(pagesInt * 0.45 + (isSoft ? 30 : 60));
    } else {
      weight = Math.round(pagesInt * 0.65 + (isSoft ? 40 : 80));
    }
    weight = pagesInt > 0 ? Math.max(50, Math.min(weight, 5000)) : 250;

    return {
      book_format_code: fmtKey || formatCode || '',
      width_mm: (hasManualW && !allowOverwriteManual) ? existingDimensions.width_mm : width,
      length_mm: (hasManualL && !allowOverwriteManual) ? existingDimensions.length_mm : length,
      height_mm: (hasManualH && !allowOverwriteManual) ? existingDimensions.height_mm : spine,
      weight_g: (hasManualWeight && !allowOverwriteManual) ? existingDimensions.weight_g : weight,
    };
  }

  /**
   * Точный расчет толщины корешка и физического веса книги по количеству страниц,
   * типу переплета и плотности бумаги.
   */
  function calculateDimensionsAndWeight(options = {}) {
    const pages = Math.max(1, parseInt(options.pages, 10) || 200);
    let w = parseInt(options.width, 10) || 130;
    let l = parseInt(options.length, 10) || 205;

    if (options.formatCode) {
      const parsed = parseFormatCode(options.formatCode);
      if (parsed) {
        w = parsed.width;
        l = parsed.length;
      }
    }
    if (w > l) { const tmp = w; w = l; l = tmp; }

    const coverVal = (options.coverType || 'Твердый переплет').toLowerCase();
    const isHard = coverVal.includes('тверд') || coverVal.includes('интегральн') || coverVal.includes('бумвинил') || coverVal.includes('кож') || coverVal.includes('тканев');

    const paperVal = (options.paperType || 'Офсетная').toLowerCase();
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

    const weight = Math.max(50, Math.round(blockWt + coverWt));

    return {
      width: w,
      length: l,
      height: spine,
      weight: weight,
    };
  }

  /**
   * Расчет габаритов и веса в упаковке (+10 мм по осям, +30 г для бандероли/пупырки Ozon).
   */
  function calcPackageDimensions(rawW, rawL, rawH, rawWt, isPkgAdder = true) {
    const w = parseInt(rawW, 10) || 130;
    const l = parseInt(rawL, 10) || 205;
    const h = parseInt(rawH, 10) || 22;
    const wt = parseInt(rawWt, 10) || 300;

    const pkgW = isPkgAdder ? (w + 10) : w;
    const pkgL = isPkgAdder ? (l + 10) : l;
    const pkgH = isPkgAdder ? (h + 10) : h;
    const pkgWt = isPkgAdder ? (wt + 30) : wt;

    return {
      width: pkgW,
      length: pkgL,
      height: pkgH,
      weight: pkgWt,
      dimensions: `${pkgW}х${pkgL}х${pkgH}`,
      rawWidth: w,
      rawLength: l,
      rawHeight: h,
      rawWeight: wt,
    };
  }

  /**
   * Расчет старой цены (до скидки) для Ozon с психологическим округлением до десятков.
   * По умолчанию наценка 40% (x1.4), но не менее чем цена + 50 руб.
   */
  function calcOldPrice(price, markupRatio = 1.4) {
    const p = parseFloat(price) || 0;
    if (p <= 0) return 0;
    const calculated = Math.round((p * markupRatio) / 10) * 10;
    return Math.max(calculated, Math.round(p + 50));
  }

  /**
   * Расчет сохранности книги (п. 5.3 спецификации).
   */
  function calculateBookCondition(hasDefects, manualCondition = '') {
    const manual = (manualCondition || '').trim().toLowerCase();
    if (manual.includes('удовл')) return 'Удовлетворительная';
    if (manual.includes('плох')) return 'Плохая';
    return hasDefects ? 'Хорошая' : 'Очень хорошая';
  }

  /**
   * Контрольная цифра GS1 EAN-13
   */
  function calcEan13Checksum(digits12) {
    const s = String(digits12).replace(/\D/g, '');
    if (s.length !== 12) return 0;
    let odd = 0, even = 0;
    for (let i = 0; i < 12; i++) {
      const d = parseInt(s[i], 10);
      if (i % 2 === 0) odd += d;
      else even += d;
    }
    const total = odd + even * 3;
    return (10 - (total % 10)) % 10;
  }

  /**
   * Генерация EAN-13 из артикула DP-B-XXXXX
   */
  function generateEan13FromArticle(article) {
    const digits = String(article || '').replace(/\D/g, '');
    let num = parseInt(digits, 10);
    if (isNaN(num) || num <= 0) num = 1;
    const numPart = String(num).padStart(6, '0');
    const base12 = `${STORE_BARCODE_PREFIX}${numPart}`.slice(-12);
    const check = calcEan13Checksum(base12);
    return `${base12}${check}`;
  }

  /**
   * Получение штрихкода EAN-13 из ISBN (10 или 13 символов).
   */
  function deriveBarcodeFromIsbn(isbn) {
    const s = String(isbn || '').trim();
    const digits = s.replace(/\D/g, '');
    if (digits.length === 13) {
      return { success: true, barcode: digits };
    }
    if (digits.length === 10) {
      const base12 = '978' + digits.substring(0, 9);
      const chk = calcEan13Checksum(base12);
      return { success: true, barcode: base12 + chk };
    }
    return {
      success: false,
      barcode: '',
      error: `В поле ISBN должно быть 10 или 13 цифр! Получено: "${s}"`,
    };
  }

  /**
   * Генерация векторного SVG штрихкода EAN-13 для этикеток Ozon
   */
  function generateEan13Svg(eanStr) {
    const ean = String(eanStr).replace(/\D/g, '');
    if (ean.length !== 13) return '';

    const L = ['0001101','0011001','0010011','0111101','0100011','0110001','0101111','0111011','0110111','0001011'];
    const G = ['0100111','0110011','0011011','0100001','0011101','0111001','0000101','0010001','0001001','0010111'];
    const R = ['1110010','1100110','1101100','1000010','1011100','1001110','1010000','1000100','1001000','1110100'];
    const PARITIES = [
      ['L','L','L','L','L','L'],
      ['L','L','G','L','G','G'],
      ['L','L','G','G','L','G'],
      ['L','L','G','G','G','L'],
      ['L','G','L','L','G','G'],
      ['L','G','G','L','L','G'],
      ['L','G','G','G','L','L'],
      ['L','G','L','G','L','G'],
      ['L','G','L','G','G','L'],
      ['L','G','G','L','G','L']
    ];

    const first = parseInt(ean[0], 10);
    const parity = PARITIES[first];
    let bitPattern = '101'; // Старт-гард

    for (let i = 1; i <= 6; i++) {
      const d = parseInt(ean[i], 10);
      const mode = parity[i - 1];
      bitPattern += (mode === 'L') ? L[d] : G[d];
    }
    bitPattern += '01010'; // Центр-гард
    for (let i = 7; i <= 12; i++) {
      const d = parseInt(ean[i], 10);
      bitPattern += R[d];
    }
    bitPattern += '101'; // Стоп-гард

    const barW = 2;
    const barH = 50;
    const guardH = 58;
    const startX = 20;

    let barsSvg = '';
    for (let i = 0; i < bitPattern.length; i++) {
      if (bitPattern[i] === '1') {
        const isGuard = (i < 3) || (i >= 45 && i < 50) || (i >= 92);
        const h = isGuard ? guardH : barH;
        barsSvg += `<rect x="${startX + i * barW}" y="5" width="${barW}" height="${h}" fill="#000000"/>`;
      }
    }

    const totalWidth = startX + bitPattern.length * barW + 15;
    return `
      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${totalWidth} 75" class="w-full h-auto">
        <rect width="${totalWidth}" height="75" fill="#ffffff"/>
        ${barsSvg}
        <text x="8" y="65" font-family="monospace" font-size="13" font-weight="bold" fill="#000000">${ean[0]}</text>
        <text x="${startX + 10}" y="68" font-family="monospace" font-size="12" font-weight="bold" letter-spacing="1.5" fill="#000000">${ean.slice(1, 7)}</text>
        <text x="${startX + 105}" y="68" font-family="monospace" font-size="12" font-weight="bold" letter-spacing="1.5" fill="#000000">${ean.slice(7, 13)}</text>
      </svg>
    `;
  }

  const BookCalculators = {
    SOVIET_FORMAT_MAP,
    STORE_BARCODE_PREFIX,
    parseFormatCode,
    calculateGostDimensions,
    calculateDimensionsAndWeight,
    calcPackageDimensions,
    calcOldPrice,
    calculateBookCondition,
    calcEan13Checksum,
    generateEan13FromArticle,
    deriveBarcodeFromIsbn,
    generateEan13Svg,
  };

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = BookCalculators;
  }
  if (typeof global !== 'undefined') {
    global.BookCalculators = BookCalculators;
  }
})(typeof window !== 'undefined' ? window : global);
