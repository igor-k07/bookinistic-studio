/**
 * api_client.js: Клиент взаимодействия с REST API Bookinistic Studio.
 * Централизует HTTP-запросы, обработку ошибок и сетевой транспорт.
 */

(function (window) {
  'use strict';

  class ApiClient {
    async request(path, options = {}) {
      const opts = {
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {}),
        },
        ...options,
      };

      try {
        const resp = await fetch(path, opts);
        if (!resp.ok) {
          let errText = `HTTP ${resp.status} ${resp.statusText}`;
          try {
            const errJson = await resp.json();
            if (errJson && errJson.error) errText = errJson.error;
          } catch (_) {}
          throw new Error(errText);
        }
        return await resp.json();
      } catch (err) {
        console.error(`[ApiClient] Ошибка запроса ${path}:`, err);
        throw err;
      }
    }

    get(path, params = null) {
      let url = path;
      if (params && typeof params === 'object') {
        const qs = new URLSearchParams();
        for (const [k, v] of Object.entries(params)) {
          if (v !== undefined && v !== null) qs.append(k, String(v));
        }
        const qsStr = qs.toString();
        if (qsStr) url += (url.includes('?') ? '&' : '?') + qsStr;
      }
      return this.request(url, { method: 'GET' });
    }

    post(path, data = {}) {
      return this.request(path, {
        method: 'POST',
        body: JSON.stringify(data),
      });
    }

    // --- Книги ---
    saveBook(bookData) {
      return this.post('/api/save_book', bookData);
    }

    getBooks(mode = 'pre2011') {
      return this.get('/api/get_books', { mode });
    }

    getNextArticle() {
      return this.get('/api/get_next_article');
    }

    getDbCatalog(mode = null, status = null, search = null) {
      return this.get('/api/get_db_catalog', { mode, status, search });
    }

    deleteBookRow(article, mode = 'pre2011') {
      return this.post('/api/delete_book_row', { article, mode });
    }

    clearExcel(mode = 'pre2011') {
      return this.post('/api/clear_excel', { mode });
    }

    // --- ИИ и фото ---
    recognizeBook(images, apiKey = '', hasIllustrations = false) {
      return this.post('/api/ai_recognize_book', {
        images,
        api_key: apiKey,
        has_illustrations: hasIllustrations,
      });
    }

    enrichBook(book, hasIllustrations = true, skipDimensions = true) {
      return this.post('/api/enrich_book', {
        book,
        has_illustrations: hasIllustrations,
        skip_dimensions: skipDimensions,
      });
    }

    classifyBatch(photos, apiKey = '') {
      return this.post('/api/ai_classify_batch', { photos, api_key: apiKey });
    }

    processPhoto(image, role = 'other', forceRembg = false) {
      return this.post('/api/ai_process_photo', {
        image,
        role,
        force_rembg: forceRembg,
      });
    }

    uploadSlotPhoto(article, title, slot, photoIndex, photo, photoId) {
      return this.post('/api/s3_upload_slot_photo', {
        article,
        title,
        slot,
        photo_index: photoIndex,
        photo,
        photo_id: photoId,
      });
    }

    // --- Черновик сессии ---
    saveSessionDraft(draftData) {
      return this.post('/api/save_session_draft', draftData);
    }

    getSessionDraft() {
      return this.get('/api/get_session_draft');
    }

    clearSessionDraft() {
      return this.post('/api/clear_session_draft');
    }

    // --- Системные функции ---
    getTunnelUrl() {
      return this.get('/api/get_tunnel_url');
    }

    restartTunnel() {
      return this.get('/api/restart_tunnel');
    }

    getReferences() {
      return this.get('/api/references');
    }

    getMemos() {
      return this.get('/api/get_memos');
    }

    getKey() {
      return this.get('/api/get_key');
    }

    saveKey(key) {
      return this.post('/api/save_key', { key });
    }

    // --- Ozon Seller API ---
    getOzonStatus() {
      return this.get('/api/ozon/status');
    }

    saveOzonKeys(clientId, apiKey) {
      return this.post('/api/ozon/save_keys', { client_id: clientId, api_key: apiKey });
    }

    startOzonImport() {
      return this.post('/api/ozon/start_import');
    }

    getOzonImportStatus() {
      return this.get('/api/ozon/import_status');
    }

    publishOzonBook(bookData) {
      return this.post('/api/ozon/publish_book', bookData);
    }

    cleanupTemp(maxAgeHours = 24.0, dryRun = false) {
      return this.post('/api/cleanup_temp', { max_age_hours: maxAgeHours, dry_run: dryRun });
    }
  }

  window.ApiClient = new ApiClient();
})(window);
