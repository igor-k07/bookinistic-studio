/**
 * test_store.js: Модульное тестирование реактивного BookStore (SSOT).
 * Запуск: node tests/test_store.js
 */

const assert = require('assert');
const fs = require('fs');
const path = require('path');

// Эмуляция глобального объекта window для браузерного скрипта
global.window = {};

// Подключаем event_bus.js
const eventBusCode = fs.readFileSync(path.join(__dirname, '../templates/static/core/event_bus.js'), 'utf8');
eval(eventBusCode);

// Подключаем store.js
const storeCode = fs.readFileSync(path.join(__dirname, '../templates/static/core/store.js'), 'utf8');
eval(storeCode);

const store = global.window.BookStore;
assert(store, 'BookStore должен быть создан в глобальном пространстве');

console.log('🧪 Запуск тестов BookStore...');

// 1. Тест инициализации
store.init();
assert.strictEqual(store.books.length, 1, 'По умолчанию должна быть 1 книга');
assert.strictEqual(store.activeId, 1, 'По умолчанию активная книга #1');
console.log('✓ 1. Инициализация успешна');

// 2. Тест setField и реактивности
let fieldChangedEvent = null;
global.window.EventBus.on('book:field_changed', (e) => {
  fieldChangedEvent = e;
});

store.setField('title', 'Мастер и Маргарита');
assert.strictEqual(store.getActiveBook().formData.title, 'Мастер и Маргарита');
assert.strictEqual(store.getActiveBook().title, 'Мастер и Маргарита');
assert(fieldChangedEvent, 'Событие book:field_changed должно быть отправлено');
assert.strictEqual(fieldChangedEvent.field, 'title');
assert.strictEqual(fieldChangedEvent.value, 'Мастер и Маргарита');
console.log('✓ 2. Обновление полей и событийная шина работают');

// 3. Тест добавления книги и переключения сессий
let switchedEvent = null;
global.window.EventBus.on('book:switched', (e) => {
  switchedEvent = e;
});

const book2 = store.addBook('DP-B-00002');
assert.strictEqual(store.books.length, 2, 'В сессии должно быть 2 книги');
assert.strictEqual(store.activeId, 2, 'Активная книга должна переключиться на #2');
assert.strictEqual(store.getActiveBook().article, 'DP-B-00002');
console.log('✓ 3. Добавление новой книги успешно');

// 4. Тест независимости данных между вкладками
store.setField('year', '1985'); // для книги 2
store.switchActiveBook(1);
assert.strictEqual(store.activeId, 1);
assert.strictEqual(store.getActiveBook().formData.title, 'Мастер и Маргарита');
assert.strictEqual(store.getActiveBook().formData.year, '', 'Год в книге 1 должен оставаться пустым');

store.switchActiveBook(2);
assert.strictEqual(store.getActiveBook().formData.year, '1985', 'Год в книге 2 должен быть 1985');
console.log('✓ 4. Изоляция данных между вкладками сессий подтверждена');

// 5. Тест слотов фотографий
const asset1 = { id: 101, url: 'blob:cover.jpg' };
store.assignSlot('cover_front', asset1);
assert.strictEqual(store.getActiveBook().slots.cover_front.id, 101);

const defectAsset = { id: 102, url: 'blob:defect.jpg' };
store.assignSlot('mantra_defects', defectAsset);
assert.strictEqual(store.getActiveBook().slots.mantra_defects.length, 1);
assert.strictEqual(store.getActiveBook().slots.mantra_defects[0].id, 102);

store.clearSlots();
assert.strictEqual(store.getActiveBook().slots.cover_front, null);
assert.strictEqual(store.getActiveBook().slots.mantra_defects.length, 0);
console.log('✓ 5. Управление слотами фотографий работает корректно');

// 6. Тест аккуратного наката данных ИИ (без затирания ручных полей)
store.switchActiveBook(1);
store.setField('author', 'М. Булгаков'); // пользователь ввел автора вручную
store.applyAiData({
  author: 'Михаил Афанасьевич Булгаков', // ИИ пытается перетереть
  year: '1967', // этого поля не было
  pages: '450'
});

assert.strictEqual(store.getActiveBook().formData.author, 'М. Булгаков', 'Ручной автор не должен перетираться ИИ');
assert.strictEqual(store.getActiveBook().formData.year, '1967', 'Новые поля от ИИ должны успешно заполняться');
assert.strictEqual(store.getActiveBook().formData.pages, '450');
console.log('✓ 6. Применение данных Gemini AI без конфликтов подтверждено');

console.log('\n🎉 Все тесты BookStore успешно пройдены!');
