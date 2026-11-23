/**
 * tests/test_calculators.js: Модульные тесты для BookCalculators и BookValidators
 * Запуск: node tests/test_calculators.js
 */

const assert = require('assert');
const path = require('path');

const BookCalculators = require(path.join(__dirname, '../templates/static/core/calculators.js'));
const BookValidators = require(path.join(__dirname, '../templates/static/core/validators.js'));

let testsPassed = 0;
let testsFailed = 0;

function it(name, fn) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    testsPassed++;
  } catch (err) {
    console.error(`  ✗ ${name}`);
    console.error(`    ${err.message}`);
    testsFailed++;
  }
}

console.log('\n--- Тестирование BookCalculators ---');

it('parseFormatCode: распознает советские типографские форматы', () => {
  const f1 = BookCalculators.parseFormatCode('84x108/32');
  assert.strictEqual(f1.key, '84x108/32');
  assert.strictEqual(f1.width, 130);
  assert.strictEqual(f1.length, 200);

  const f2 = BookCalculators.parseFormatCode('формат 60×90 1/16');
  assert.strictEqual(f2.key, '60x90/16');
  assert.strictEqual(f2.width, 145);
  assert.strictEqual(f2.length, 215);

  const f3 = BookCalculators.parseFormatCode('неизвестный формат');
  assert.strictEqual(f3, null);
});

it('calcPackageDimensions: добавляет поля упаковки Ozon (+10 мм, +30 г)', () => {
  const pkg = BookCalculators.calcPackageDimensions(130, 205, 20, 300, true);
  assert.strictEqual(pkg.width, 140);
  assert.strictEqual(pkg.length, 215);
  assert.strictEqual(pkg.height, 30);
  assert.strictEqual(pkg.weight, 330);
  assert.strictEqual(pkg.dimensions, '140х215х30');

  const noPkg = BookCalculators.calcPackageDimensions(130, 205, 20, 300, false);
  assert.strictEqual(noPkg.width, 130);
  assert.strictEqual(noPkg.length, 205);
  assert.strictEqual(noPkg.height, 20);
  assert.strictEqual(noPkg.weight, 300);
});

it('calcOldPrice: рассчитывает старую цену x1.4 с округлением до 10 руб', () => {
  assert.strictEqual(BookCalculators.calcOldPrice(1000), 1400);
  assert.strictEqual(BookCalculators.calcOldPrice(750), 1050);
  // Минимальная разница +50 руб для малых цен
  assert.strictEqual(BookCalculators.calcOldPrice(80), 130);
  assert.strictEqual(BookCalculators.calcOldPrice(0), 0);
});

it('calculateBookCondition: корректно определяет сохранность по наличию дефектов', () => {
  assert.strictEqual(BookCalculators.calculateBookCondition(false), 'Очень хорошая');
  assert.strictEqual(BookCalculators.calculateBookCondition(true), 'Хорошая');
  assert.strictEqual(BookCalculators.calculateBookCondition(false, 'Удовлетворительная'), 'Удовлетворительная');
  assert.strictEqual(BookCalculators.calculateBookCondition(true, 'Удовлетворительная'), 'Удовлетворительная');
});

it('calcEan13Checksum и generateEan13FromArticle: создает валидный GS1 EAN-13', () => {
  const ean = BookCalculators.generateEan13FromArticle('DP-B-03098');
  assert.strictEqual(ean.length, 13);
  assert.ok(ean.startsWith('297847'));
  const checkDigit = BookCalculators.calcEan13Checksum(ean.slice(0, 12));
  assert.strictEqual(parseInt(ean[12], 10), checkDigit);
});

it('deriveBarcodeFromIsbn: извлекает EAN-13 из 10- и 13-значного ISBN', () => {
  const res13 = BookCalculators.deriveBarcodeFromIsbn('978-5-17-147716-5');
  assert.strictEqual(res13.success, true);
  assert.strictEqual(res13.barcode, '9785171477165');

  const res10 = BookCalculators.deriveBarcodeFromIsbn('0-306-40615-2');
  assert.strictEqual(res10.success, true);
  assert.strictEqual(res10.barcode.length, 13);
  assert.ok(res10.barcode.startsWith('978030640615'));

  const resInvalid = BookCalculators.deriveBarcodeFromIsbn('12345');
  assert.strictEqual(resInvalid.success, false);
});


console.log('\n--- Тестирование BookValidators ---');

it('resolveTemplateMode: определяет pre2011 vs post2011', () => {
  assert.strictEqual(BookValidators.resolveTemplateMode(1985), 'pre2011');
  assert.strictEqual(BookValidators.resolveTemplateMode(2011), 'pre2011');
  assert.strictEqual(BookValidators.resolveTemplateMode(2012), 'post2011');
  assert.strictEqual(BookValidators.resolveTemplateMode(2024), 'post2011');
  assert.strictEqual(BookValidators.resolveTemplateMode(null), 'pre2011');
});

it('validateIsbn: валидирует ISBN-10 (включая контрольный символ X)', () => {
  // 0-306-40615-2 (валидный ISBN-10)
  const v1 = BookValidators.validateIsbn('0-306-40615-2', 1995);
  assert.strictEqual(v1.isValid, true);
  assert.strictEqual(v1.isIsbn10, true);

  // 0-8044-2957-X (валидный ISBN-10 с X)
  const vX = BookValidators.validateIsbn('0-8044-2957-X', 1980);
  assert.strictEqual(vX.isValid, true);
  assert.strictEqual(vX.isIsbn10, true);

  // Невалидный ISBN-10
  const vBad = BookValidators.validateIsbn('0-306-40615-3', 1995);
  assert.strictEqual(vBad.isValid, false);
});

it('validateIsbn: валидирует ISBN-13', () => {
  const v13 = BookValidators.validateIsbn('978-5-17-147716-5', 2022);
  assert.strictEqual(v13.isValid, true);
  assert.strictEqual(v13.isIsbn13, true);

  const vBad13 = BookValidators.validateIsbn('978-5-17-147716-9', 2022);
  assert.strictEqual(vBad13.isValid, false);
});

it('validateIsbn: пустой ISBN допустим до 2011 г. и запрещен после 2011 г.', () => {
  const pre = BookValidators.validateIsbn('', 1975);
  assert.strictEqual(pre.isValid, true);
  assert.strictEqual(pre.isRequired, false);

  const post = BookValidators.validateIsbn('', 2018);
  assert.strictEqual(post.isValid, false);
  assert.strictEqual(post.isRequired, true);
});

it('validateBookForOzon: выявляет пропущенные обязательные поля', () => {
  // Пустая книга
  const emptyRes = BookValidators.validateBookForOzon({});
  assert.strictEqual(emptyRes.isValid, false);
  assert.ok(emptyRes.errors.some(e => e.includes('название')));
  assert.ok(emptyRes.errors.some(e => e.includes('автор')));
  assert.ok(emptyRes.errors.some(e => e.includes('фото')));

  // Полная валидная книга до 2011 года
  const validPreBook = {
    title: 'Капитанская дочка',
    author: 'Александр Пушкин',
    year: '1984',
    price: '450',
    width: 130,
    length: 200,
    height: 15,
    weight: 250,
    article: 'DP-B-00001',
    slots: {
      cover_front: { id: 1, name: 'cover.jpg' }
    }
  };
  const valRes = BookValidators.validateBookForOzon(validPreBook);
  assert.strictEqual(valRes.isValid, true);
  assert.strictEqual(valRes.errors.length, 0);

  // Книга 2020 года без ISBN должна иметь ошибку
  const postBookNoIsbn = {
    ...validPreBook,
    year: '2020',
    isbn: ''
  };
  const postRes = BookValidators.validateBookForOzon(postBookNoIsbn);
  assert.strictEqual(postRes.isValid, false);
  assert.ok(postRes.errors.some(e => e.includes('ISBN')));
});

console.log(`\nРЕЗУЛЬТАТ: ${testsPassed} успешно, ${testsFailed} провалено.\n`);
if (testsFailed > 0) process.exit(1);
