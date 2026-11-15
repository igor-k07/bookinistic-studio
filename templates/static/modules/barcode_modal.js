/**
 * barcode_modal.js: Модальное окно штрихкодов EAN-13, термоэтикетка и печать 58х40 мм.
 */

(function (window) {
  'use strict';

  function generateBarcodeForCurrentBook() {
    const artInput = document.getElementById('article');
    let art = artInput ? artInput.value.trim() : '';
    if (!art) {
      art = 'DP-B-00001';
      if (artInput) artInput.value = art;
    }
    const barcode = window.BookCalculators
      ? window.BookCalculators.generateEan13FromArticle(art)
      : (window.generateEan13FromArticle ? window.generateEan13FromArticle(art) : '2978470000012');

    const bcInput = document.getElementById('barcode');
    if (bcInput) {
      bcInput.value = barcode;
      bcInput.classList.add('field-updated');
      setTimeout(() => bcInput.classList.remove('field-updated'), 1000);
    }
    const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
    if (book) {
      if (!book.formData) book.formData = {};
      book.formData.barcode = barcode;
    }
    if (typeof scheduleAutoSave === 'function') scheduleAutoSave();
  }

  function openBarcodeModal() {
    const book = typeof getActiveBook === 'function' ? getActiveBook() : null;
    let art = document.getElementById('article')?.value.trim() || (book?.formData?.article) || 'DP-B-00001';
    let bc = document.getElementById('barcode')?.value.trim() || (book?.formData?.barcode) || '';
    if (!bc || bc === 'генерирует озон' || !/^\d{12,13}$/.test(bc)) {
      bc = window.BookCalculators ? window.BookCalculators.generateEan13FromArticle(art) : '2978470000012';
      const bcInput = document.getElementById('barcode');
      if (bcInput) bcInput.value = bc;
    }
    const title = document.getElementById('title')?.value.trim() || (book?.formData?.title) || 'Книга';
    const author = document.getElementById('author')?.value.trim() || document.getElementById('author_cover')?.value.trim() || (book?.formData?.author) || '';
    const price = document.getElementById('price')?.value.trim() || (book?.formData?.price) || '350';

    const labelTitle = document.getElementById('labelTitle');
    const labelAuthor = document.getElementById('labelAuthor');
    const labelArticle = document.getElementById('labelArticle');
    const labelPrice = document.getElementById('labelPrice');
    const labelEanText = document.getElementById('labelEanText');
    const svgBox = document.getElementById('barcodeSvgContainer');

    if (labelTitle) labelTitle.textContent = title;
    if (labelAuthor) labelAuthor.textContent = author || 'Букинистика';
    if (labelArticle) labelArticle.textContent = art;
    if (labelPrice) labelPrice.textContent = price ? `${price} ₽` : '350 ₽';
    if (labelEanText) labelEanText.textContent = bc;
    if (svgBox) {
      svgBox.innerHTML = window.BookCalculators ? window.BookCalculators.generateEan13Svg(bc) : '';
    }

    const modal = document.getElementById('barcodeModal');
    if (modal) modal.classList.remove('hidden');
  }

  function closeBarcodeModal() {
    const modal = document.getElementById('barcodeModal');
    if (modal) modal.classList.add('hidden');
  }

  function printBarcodeLabel() {
    window.print();
  }

  async function copyBarcodeText() {
    const el = document.getElementById('labelEanText');
    const bc = el ? el.textContent.trim() : '';
    try {
      await navigator.clipboard.writeText(bc);
      const icon = document.getElementById('copyBarcodeIcon');
      const text = document.getElementById('copyBarcodeBtnText');
      if (icon) icon.textContent = '✅';
      if (text) text.textContent = 'Скопировано!';
      setTimeout(() => {
        if (icon) icon.textContent = '📋';
        if (text) text.textContent = 'Копировать код';
      }, 1500);
    } catch (e) {
      alert(`Штрихкод: ${bc}`);
    }
  }

  window.generateBarcodeForCurrentBook = generateBarcodeForCurrentBook;
  window.openBarcodeModal = openBarcodeModal;
  window.closeBarcodeModal = closeBarcodeModal;
  window.printBarcodeLabel = printBarcodeLabel;
  window.copyBarcodeText = copyBarcodeText;
})(window);

