/**
 * tests/test_book_form.js: Модульные тесты для BookForm
 * Запуск: node tests/test_book_form.js
 */

const assert = require('assert');
const path = require('path');

// Минимальный мок DOM-окружения для тестирования в Node.js
class MockElement {
  constructor(tagName, id, fieldName, type = 'text') {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.type = type;
    this.value = '';
    this.checked = false;
    this.attributes = { 'data-field': fieldName, id };
    this.classList = {
      add: () => {},
      remove: () => {},
    };
  }

  getAttribute(name) {
    return this.attributes[name] || null;
  }

  matches(selector) {
    const sel = selector.toLowerCase();
    return sel.includes(this.tagName.toLowerCase());
  }
}

class MockContainer {
  constructor() {
    this.listeners = {};
    this.elements = [];
  }

  addEventListener(event, fn) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(fn);
  }

  trigger(event, eventObj) {
    (this.listeners[event] || []).forEach(fn => fn(eventObj));
  }

  querySelectorAll() {
    return this.elements;
  }

  querySelector() {
    return this;
  }
}

// Создаем тестовую форму
const mockContainer = new MockContainer();
const titleEl = new MockElement('input', 'title', 'title');
const authorEl = new MockElement('input', 'author', 'author');
const yearEl = new MockElement('input', 'year', 'year');
const priceEl = new MockElement('input', 'price', 'price');
const pkgCheckEl = new MockElement('input', 'autoPackageAdder', 'auto_package_adder', 'checkbox');
pkgCheckEl.checked = true;

mockContainer.elements.push(titleEl, authorEl, yearEl, priceEl, pkgCheckEl);

global.document = {
  querySelector: () => mockContainer,
  getElementById: (id) => mockContainer.elements.find(el => el.id === id),
  activeElement: null,
};

// Шина событий мок
const eventListeners = {};
global.EventBus = {
  on: (ev, fn) => {
    if (!eventListeners[ev]) eventListeners[ev] = [];
    eventListeners[ev].push(fn);
  },
  emit: (ev, data) => {
    (eventListeners[ev] || []).forEach(fn => fn(data));
  }
};

let storeFieldUpdates = {};
global.BookStore = {
  activeId: 1,
  setField: (f, v) => { storeFieldUpdates[f] = v; },
  updateFields: (fields) => { Object.assign(storeFieldUpdates, fields); },
};

const { BookForm } = require(path.join(__dirname, '../templates/static/modules/book_form.js'));

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

console.log('\n--- Тестирование BookForm ---');

const form = new BookForm();
form.init('#ozonFormContainer');

it('1. Инициализация и кеширование элементов формы', () => {
  assert.strictEqual(form.initialized, true);
  assert.strictEqual(form.fieldsMap.get('title'), titleEl);
  assert.strictEqual(form.fieldsMap.get('author'), authorEl);
  assert.strictEqual(form.fieldsMap.get('auto_package_adder'), pkgCheckEl);
});

it('2. populateForm заполняет поля и чекбоксы', () => {
  form.populateForm({
    title: 'Евгений Онегин',
    author: 'Александр Пушкин',
    year: '1984',
    price: '500',
    auto_package_adder: false,
  });

  assert.strictEqual(titleEl.value, 'Евгений Онегин');
  assert.strictEqual(authorEl.value, 'Александр Пушкин');
  assert.strictEqual(yearEl.value, '1984');
  assert.strictEqual(priceEl.value, '500');
  assert.strictEqual(pkgCheckEl.checked, false);
});

it('3. readForm читает все поля в чистый объект', () => {
  const data = form.readForm();
  assert.strictEqual(data.title, 'Евгений Онегин');
  assert.strictEqual(data.author, 'Александр Пушкин');
  assert.strictEqual(data.price, '500');
  assert.strictEqual(data.auto_package_adder, false);
});

it('4. Делегирование пользовательского ввода в BookStore', () => {
  titleEl.value = 'Капитанская дочка';
  mockContainer.trigger('input', { target: titleEl });
  assert.strictEqual(storeFieldUpdates.title, 'Капитанская дочка');
});

it('5. Реакция на переключение книги через EventBus book:switched', () => {
  global.EventBus.emit('book:switched', {
    bookId: 2,
    book: {
      id: 2,
      formData: {
        title: 'Дубровский',
        author: 'Пушкин А.С.',
        price: '350',
      }
    }
  });

  assert.strictEqual(titleEl.value, 'Дубровский');
  assert.strictEqual(authorEl.value, 'Пушкин А.С.');
  assert.strictEqual(priceEl.value, '350');
});

it('6. clearForm очищает поля', () => {
  form.clearForm({ auto_package_adder: true });
  assert.strictEqual(titleEl.value, '');
  assert.strictEqual(authorEl.value, '');
  assert.strictEqual(priceEl.value, '');
  assert.strictEqual(pkgCheckEl.checked, true);
});

console.log(`\nРЕЗУЛЬТАТ: ${testsPassed} успешно, ${testsFailed} провалено.\n`);
if (testsFailed > 0) process.exit(1);
