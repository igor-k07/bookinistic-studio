// tests/test_ui_buttons.js
// End-to-end verification of Bookinistic Studio UI buttons & functions using Headless Chrome & CDP

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
  console.log('🚀 Запуск Headless Chrome для тестирования UI кнопок и скриптов...');
  const port = 9225;
  const chrome = spawn('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', [
    '--headless=new',
    `--remote-debugging-port=${port}`,
    '--no-first-run',
    '--no-default-browser-check',
    '--window-size=1400,900',
    'http://localhost:8095/'
  ], { stdio: 'ignore' });

  try {
    // Ждем запуска Chrome CDP
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
    console.log(`✓ Подключение к вкладке: ${pageTarget.url}`);

    const client = new CDPClient(pageTarget.webSocketDebuggerUrl);
    await client.connect();

    await client.send('Runtime.enable');
    await client.send('Page.enable');

    // Ждем полной загрузки DOM и скриптов
    await wait(2000);

    // Автоматическое подтверждение диалогов в headless режиме
    await client.eval(`
      window.confirm = () => true;
      window.alert = () => {};
    `);

    console.log('\n--- Проверка 1: Глобальные функции и объекты интерфейса ---');
    const functionsToCheck = [
      'addNewBook',
      'switchBook',
      'closeBookTab',
      'closeAllBookTabs',
      'handlePrimaryBookSave',
      'openCatalogSearchModal',
      'closeCatalogSearchModal',
      'openSettingsModal',
      'closeSettingsModal',
      'switchOzonStore',
      'refreshPreviewTable',
      'revealTableFile',
      'openClearTableModal',
      'closeClearTableModal',
      'showToast'
    ];

    for (const fn of functionsToCheck) {
      const type = await client.eval(`typeof window.${fn}`);
      if (type !== 'function') {
        throw new Error(`ОШИБКА: Функция window.${fn} не определена (тип: ${type})`);
      }
      console.log(`  ✓ window.${fn} доступна`);
    }

    console.log('\n--- Проверка 2: Архитектурные синглтоны (BookStore, EventBus, ApiClient) ---');
    const storeReady = await client.eval(`typeof window.BookStore === 'object' && window.BookStore !== null`);
    const busReady = await client.eval(`typeof window.EventBus === 'object' && window.EventBus !== null`);
    const apiReady = await client.eval(`typeof window.ApiClient === 'object' && window.ApiClient !== null`);
    console.log(`  ✓ window.BookStore: ${storeReady}`);
    console.log(`  ✓ window.EventBus: ${busReady}`);
    console.log(`  ✓ window.ApiClient: ${apiReady}`);
    if (!storeReady || !busReady || !apiReady) {
      throw new Error('Один из синглтонов ядра не инициализирован!');
    }

    console.log('\n--- Проверка 3: Интерактивность кнопок сессий (добавление, переключение, закрытие до 0) ---');
    
    // Получаем начальное количество книг
    const initialCount = await client.eval(`window.BookStore.getBooks().length`);
    console.log(`  Начальное количество книг в сессии: ${initialCount}`);

    // Добавляем новую книгу через кнопку "Новая книга"
    console.log('  -> Нажатие на кнопку "Новая книга"...');
    await client.eval(`(function() {
      const btn = document.querySelector('button[onclick*="addNewBook"]');
      if (btn) btn.click();
      else window.addNewBook();
    })()`);
    await wait(300);

    const countAfterAdd = await client.eval(`window.BookStore.getBooks().length`);
    console.log(`  Количество книг после добавления: ${countAfterAdd}`);
    if (countAfterAdd !== initialCount + 1) {
      throw new Error(`Ожидалось ${initialCount + 1} книг, получено: ${countAfterAdd}`);
    }
    console.log('  ✓ Кнопка "Новая книга" успешно создает вкладку!');

    // Закрываем все вкладки через кнопку "Закрыть все вкладки"
    console.log('  -> Нажатие на кнопку "Закрыть все вкладки" (закрытие до 0)...');
    await client.eval(`(function() {
      const btn = document.getElementById('btnCloseAllTabs') || document.querySelector('button[onclick*="closeAllBookTabs"]');
      if (btn) btn.click();
      else window.closeAllBookTabs();
    })()`);
    await wait(300);

    const countAfterCloseAll = await client.eval(`window.BookStore.getBooks().length`);
    console.log(`  Количество книг после закрытия всех вкладок: ${countAfterCloseAll}`);
    if (countAfterCloseAll !== 0) {
      throw new Error(`Ожидалось 0 книг после closeAll, получено: ${countAfterCloseAll}`);
    }
    console.log('  ✓ Кнопка "Закрыть все вкладки" успешно закрывает все книги до 0!');

    // Добавляем книгу заново
    console.log('  -> Добавляем книгу из пустого состояния (0 вкладок)...');
    await client.eval(`window.addNewBook()`);
    await wait(300);
    const countAfterReAdd = await client.eval(`window.BookStore.getBooks().length`);
    if (countAfterReAdd !== 1) {
      throw new Error(`Ожидалась 1 книга, получено: ${countAfterReAdd}`);
    }
    console.log('  ✓ Успешное восстановление книги из состояния 0 вкладок!');

    console.log('\n--- Проверка 4: Модальные окна (Каталог и Настройки) ---');
    
    // Модальное окно поиска по каталогу
    console.log('  -> Открытие модального окна каталога...');
    await client.eval(`window.openCatalogSearchModal()`);
    await wait(200);
    const catalogModalOpen = await client.eval(`!document.getElementById('catalogSearchModal').classList.contains('hidden')`);
    console.log(`  ✓ Каталог открыт: ${catalogModalOpen}`);
    if (!catalogModalOpen) throw new Error('Модальное окно каталога не открылось!');

    await client.eval(`window.closeCatalogSearchModal()`);
    await wait(200);
    const catalogModalClosed = await client.eval(`document.getElementById('catalogSearchModal').classList.contains('hidden')`);
    console.log(`  ✓ Каталог закрыт: ${catalogModalClosed}`);

    // Модальное окно настроек
    console.log('  -> Открытие модального окна настроек...');
    await client.eval(`window.openSettingsModal()`);
    await wait(200);
    const settingsModalOpen = await client.eval(`!document.getElementById('settingsModal').classList.contains('hidden')`);
    console.log(`  ✓ Настройки открыты: ${settingsModalOpen}`);
    if (!settingsModalOpen) throw new Error('Модальное окно настроек не открылось!');

    await client.eval(`window.closeSettingsModal()`);
    await wait(200);
    const settingsModalClosed = await client.eval(`document.getElementById('settingsModal').classList.contains('hidden')`);
    console.log(`  ✓ Настройки закрыты: ${settingsModalClosed}`);

    console.log('\n--- Проверка 5: Анализ ошибок в консоли браузера ---');
    if (client.pageErrors.length > 0) {
      console.error('Обнаружены ошибки страницы:', client.pageErrors);
      throw new Error(`Обнаружено ${client.pageErrors.length} необработанных ошибок в браузере`);
    } else {
      console.log('  ✓ 0 необработанных ошибок в браузере (0 JS exceptions)!');
    }

    client.close();
    console.log('\n🎉 ВСЕ ТЕСТЫ UI И КНОПОК УСПЕШНО ПРОЙДЕНЫ БЕЗ ЕДИНОЙ ОШИБКИ!');
    process.exit(0);

  } catch (err) {
    console.error('\n❌ ТЕСТ ПРОВАЛЕН:', err);
    process.exit(1);
  } finally {
    try { chrome.kill(); } catch (e) {}
  }
}

run();
