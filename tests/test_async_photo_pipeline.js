// tests/test_async_photo_pipeline.js
// Verification of non-blocking photo slots, preloading, and parallel AI execution

const { spawn } = require('child_process');
const http = require('http');

function wait(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function fetchJson(url) {
  return new Promise((resolve, reject) => {
    http.get(url, res => {
      let data = '';
      res.on('data', chunk => (data += chunk));
      res.on('end', () => {
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(e);
        }
      });
    }).on('error', reject);
  });
}

class CDPClient {
  constructor(wsUrl) {
    this.wsUrl = wsUrl;
    this.ws = null;
    this.id = 1;
    this.callbacks = new Map();
    this.consoleLogs = [];
    this.pageErrors = [];
  }

  connect() {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(this.wsUrl);
      this.ws.onopen = () => resolve();
      this.ws.onerror = err => reject(err);
      this.ws.onmessage = evt => {
        const msg = JSON.parse(evt.data);
        if (msg.method === 'Runtime.consoleAPICalled') {
          this.consoleLogs.push(msg.params);
        }
        if (msg.method === 'Runtime.exceptionThrown') {
          this.pageErrors.push(msg.params.exceptionDetails);
        }
        if (msg.id && this.callbacks.has(msg.id)) {
          const cb = this.callbacks.get(msg.id);
          this.callbacks.delete(msg.id);
          cb(msg);
        }
      };
    });
  }

  send(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = this.id++;
      this.callbacks.set(id, msg => {
        if (msg.error) reject(new Error(msg.error.message));
        else resolve(msg.result);
      });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async eval(expression) {
    const res = await this.send('Runtime.evaluate', {
      expression,
      returnByValue: true,
      awaitPromise: true
    });
    if (res.exceptionDetails) {
      throw new Error(`Eval failed: ${res.exceptionDetails.text} (${expression})`);
    }
    return res.result?.value;
  }

  close() {
    if (this.ws) this.ws.close();
  }
}

async function run() {
  console.log('🚀 Тестирование неблокирующего фото-конвейера и параллельности ИИ...');
  const port = 9226;
  const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
    '--headless=new',
    `--remote-debugging-port=${port}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--incognito',
    '--disable-cache',
    '--user-data-dir=/tmp/test_chrome_profile_async',
    '--window-size=1400,900',
    'http://localhost:8095/'
  ], { stdio: 'ignore' });

  try {
    let targets = null;
    for (let i = 0; i < 30; i++) {
      await wait(300);
      try {
        targets = await fetchJson(`http://127.0.0.1:${port}/json`);
        if (targets && targets.length > 0) break;
      } catch (e) {}
    }

    if (!targets || targets.length === 0) {
      throw new Error('Chrome не ответил по CDP');
    }

    const pageTarget = targets.find(t => t.type === 'page' && t.url.includes('localhost:8095')) || targets[0];
    const client = new CDPClient(pageTarget.webSocketDebuggerUrl);
    await client.connect();

    await client.send('Runtime.enable');
    await client.send('Page.enable');
    await wait(2000);

    await client.eval(`
      window.confirm = () => true;
      window.alert = () => {};
    `);

    console.log('\n--- Тест 1: Свободное перетаскивание при фоновой обработке (draggable="true") ---');
    // Добавляем тестовое фото в пул и в слот с флагом isAiProcessing = true
    const testResult = await client.eval(`(function() {
      const book = window.getActiveBook();
      if (!book) return { success: false, error: 'No active book' };

      const testPhoto = {
        id: 'test_ast_1',
        name: 'test_cover.jpg',
        preview: '/card.png',
        cameraOriginal: '/card.png',
        rawOriginal: '/card.png',
        isAiProcessing: true,
        assignedBookId: book.id,
        assignedSlot: 'cover_front'
      };

      book.slots.cover_front = testPhoto;
      window.renderActiveBookSlots();

      const slotEl = document.getElementById('slot_cover_front');
      const card = slotEl.querySelector('[draggable]');
      const isDraggable = card ? card.getAttribute('draggable') : null;
      const hasDarkCurtain = card ? Boolean(card.querySelector('.bg-slate-950\\\\/70')) : false;
      const hasAiBadge = card ? Boolean(card.textContent.includes('ИИ') || card.textContent.includes('ВЫРЕЗАЕТ') || card.textContent.includes('rembg')) : false;

      return {
        success: true,
        isDraggable,
        hasDarkCurtain,
        hasAiBadge
      };
    })()`);

    console.log('  Результат слота при isAiProcessing:', testResult);
    if (testResult.isDraggable !== 'true') {
      throw new Error(`ОШИБКА: Карточка в слоте заблокирована для перетаскивания (draggable="${testResult.isDraggable}")!`);
    }
    if (testResult.hasDarkCurtain) {
      throw new Error('ОШИБКА: Обнаружена затемняющая плашка bg-slate-950/70, перекрывающая картинку!');
    }
    if (!testResult.hasAiBadge) {
      throw new Error('ОШИБКА: Не отображается статус фоновой обработки ИИ!');
    }
    console.log('  ✓ Карточка остается 100% перетаскиваемой (draggable="true") и картинка видна без затемнения!');

    console.log('\n--- Тест 2: Свободное перетаскивание при распознавании книги Gemini ---');
    const geminiTestResult = await client.eval(`(function() {
      const book = window.getActiveBook();
      book.isAiRecognizing = true;
      window.isBookAiRecognizing = true;
      window.renderActiveBookSlots();

      const slotEl = document.getElementById('slot_cover_front');
      const card = slotEl.querySelector('[draggable]');
      const isDraggable = card ? card.getAttribute('draggable') : null;
      const hasDarkCurtain = card ? Boolean(card.querySelector('.bg-slate-950\\\\/70')) : false;

      // Сбрасываем флаг
      book.isAiRecognizing = false;
      window.isBookAiRecognizing = false;
      window.renderActiveBookSlots();

      return {
        isDraggable,
        hasDarkCurtain
      };
    })()`);

    console.log('  Результат слота при анализе Gemini:', geminiTestResult);
    if (geminiTestResult.isDraggable !== 'true') {
      throw new Error(`ОШИБКА: Карточка заблокирована при анализе Gemini (draggable="${geminiTestResult.isDraggable}")!`);
    }
    if (geminiTestResult.hasDarkCurtain) {
      throw new Error('ОШИБКА: Темный экран блокирует просмотр книги при анализе Gemini!');
    }
    console.log('  ✓ При анализе книги Gemini фото не блокируются и не перекрываются черной ширмой!');

    console.log('\n--- Тест 3: Независимость вкладок нескольких книг при фоновом ИИ ---');
    const multiTabResult = await client.eval(`(async function() {
      // Создаем вторую книгу асинхронно
      await window.addNewBook();
      const books = window.BookStore ? window.BookStore.getBooks() : window.booksSession;
      if (books.length < 2) return { success: false, error: 'Less than 2 books' };

      const book1 = books[0];
      const book2 = books[1];

      // Запускаем симуляцию фонового распознавания для книги 1
      book1.isAiRecognizing = true;

      // Переключаемся на книгу 2
      window.switchBook(book2.id);

      const activeId = window.activeBookId;
      const isCurBookRecognizing = Boolean(window.isBookAiRecognizing);

      // Сбрасываем состояние
      book1.isAiRecognizing = false;

      return {
        success: true,
        activeId,
        book2Id: book2.id,
        isCurBookRecognizing
      };
    })()`);

    console.log('  Результат переключения при фоновом ИИ:', multiTabResult);
    if (multiTabResult.activeId !== multiTabResult.book2Id) {
      throw new Error('ОШИБКА: Не удалось переключить активную книгу!');
    }
    if (multiTabResult.isCurBookRecognizing !== false) {
      throw new Error('ОШИБКА: Книга 2 унаследовала статус занятости от Книги 1!');
    }
    console.log('  ✓ Вторая книга полностью независима и не блокируется фоновой работой первой книги!');

    console.log('\n--- Тест 4: Проверка консоли браузера на ошибки ---');
    if (client.pageErrors.length > 0) {
      console.error('Обнаружены ошибки страницы:', client.pageErrors);
      throw new Error(`Обнаружено ${client.pageErrors.length} необработанных ошибок в браузере`);
    }
    console.log('  ✓ 0 необработанных ошибок в консоли!');

    client.close();
    console.log('\n🎉 ВСЕ ТЕСТЫ НЕБЛОКИРУЮЩЕГО ФОТО-КОНВЕЙЕРА И ПАРАЛЛЕЛЬНОСТИ ИИ УСПЕШНО ПРОЙДЕНЫ!');
    process.exit(0);

  } catch (err) {
    console.error('\n❌ ТЕСТ ПРОВАЛЕН:', err);
    process.exit(1);
  } finally {
    try { chrome.kill(); } catch (e) {}
  }
}

run();
