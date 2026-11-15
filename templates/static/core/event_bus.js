/**
 * event_bus.js: Легковесная шина событий (Publish/Subscribe) для Bookinistic Studio.
 * Отвязывает компоненты интерфейса (фоторедактор, ленту, слоты, форму) от прямого вызова чужих функций.
 */

(function (window) {
  'use strict';

  class EventBus {
    constructor() {
      this.listeners = new Map();
    }

    /**
     * Подписка на событие
     * @param {string} event 
     * @param {Function} callback 
     * @returns {Function} функция отписки
     */
    on(event, callback) {
      if (typeof callback !== 'function') return () => {};
      if (!this.listeners.has(event)) {
        this.listeners.set(event, new Set());
      }
      this.listeners.get(event).add(callback);
      return () => this.off(event, callback);
    }

    /**
     * Однократная подписка
     */
    once(event, callback) {
      const unsubscribe = this.on(event, (...args) => {
        unsubscribe();
        callback(...args);
      });
      return unsubscribe;
    }

    /**
     * Отписка от события
     */
    off(event, callback) {
      if (!this.listeners.has(event)) return;
      this.listeners.get(event).delete(callback);
      if (this.listeners.get(event).size === 0) {
        this.listeners.delete(event);
      }
    }

    /**
     * Публикация события
     */
    emit(event, data) {
      if (!this.listeners.has(event)) return;
      for (const callback of this.listeners.get(event)) {
        try {
          callback(data);
        } catch (err) {
          console.error(`[EventBus] Ошибка в обработчике события '${event}':`, err);
        }
      }
    }

    /**
     * Очистка всех слушателей
     */
    clear() {
      this.listeners.clear();
    }
  }

  window.EventBus = new EventBus();
})(window);
