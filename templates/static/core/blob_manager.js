/**
 * blob_manager.js: Управление Blob URL и освобождением оперативной памяти браузера.
 * Реализует п. 6 спецификации: исключение Base64-строк из DOM для предотвращения утечек RAM.
 */

(function (window) {
  'use strict';

  class BlobManager {
    constructor() {
      // Карта: base64_hash / photo_id -> blob_url
      this.blobCache = new Map();
      this.activeBlobUrls = new Set();
    }

    /**
     * Конвертирует base64-строку (или data-URI) в бинарный Blob.
     */
    base64ToBlob(base64Data, defaultMime = 'image/jpeg') {
      if (!base64Data || typeof base64Data !== 'string') return null;

      let mime = defaultMime;
      let rawBase64 = base64Data;

      if (base64Data.startsWith('data:')) {
        const parts = base64Data.split(',', 2);
        const match = parts[0].match(/:(.*?);/);
        if (match) mime = match[1];
        rawBase64 = parts[1] || '';
      }

      try {
        const byteCharacters = atob(rawBase64);
        const byteNumbers = new Uint8Array(byteCharacters.length);
        for (let i = 0; i < byteCharacters.length; i++) {
          byteNumbers[i] = byteCharacters.charCodeAt(i);
        }
        return new Blob([byteNumbers], { type: mime });
      } catch (e) {
        console.warn('[BlobManager] Ошибка декодирования base64:', e);
        return null;
      }
    }

    /**
     * Возвращает эффективный Blob URL для отображения в DOM (<img> или background-image).
     * Если фото уже имеет URL на сервере (например /session_photos/...), возвращает его.
     */
    getDisplayUrl(photoObj) {
      if (!photoObj) return '';

      // 1. Если есть готовый локальный серверный URL или S3 URL
      if (photoObj.url && (photoObj.url.startsWith('/') || photoObj.url.startsWith('http'))) {
        return photoObj.url;
      }

      // 2. Если есть закэшированный blob URL
      const cacheKey = photoObj.id || (photoObj.name + '_' + (photoObj.data ? photoObj.data.length : 0));
      if (this.blobCache.has(cacheKey)) {
        return this.blobCache.get(cacheKey);
      }

      // 3. Если передан Base64 data или preview
      const b64 = photoObj.preview || photoObj.data;
      if (b64 && b64.startsWith('data:')) {
        const blob = this.base64ToBlob(b64);
        if (blob) {
          const blobUrl = URL.createObjectURL(blob);
          this.blobCache.set(cacheKey, blobUrl);
          this.activeBlobUrls.add(blobUrl);
          return blobUrl;
        }
      }

      return b64 || '';
    }

    /**
     * Освобождает память браузера, отзывая неиспользуемый Blob URL.
     */
    revoke(photoIdOrKey) {
      if (this.blobCache.has(photoIdOrKey)) {
        const url = this.blobCache.get(photoIdOrKey);
        URL.revokeObjectURL(url);
        this.activeBlobUrls.delete(url);
        this.blobCache.delete(photoIdOrKey);
      }
    }

    /**
     * Полная очистка всех зарегистрированных Blob URL при сбросе сессии.
     */
    revokeAll() {
      for (const url of this.activeBlobUrls) {
        try {
          URL.revokeObjectURL(url);
        } catch (e) {}
      }
      this.blobCache.clear();
      this.activeBlobUrls.clear();
    }
  }

  window.BlobManager = new BlobManager();
})(window);
