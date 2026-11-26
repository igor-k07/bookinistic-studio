/**
 * BookForm — Complete 40+ field Ozon Book Form (1:1 business logic parity with v1 desktop.html).
 */

import React, { useEffect } from "react";
import { useSystemStore } from "../../store/systemStore";
import { useWorkspaceStore } from "../../store/workspaceStore";
import { BookFormRightCol } from "./BookFormRightCol";
import { generateEan13FromArticle } from "./ozonCatalogOptions";
import { PublishingSection } from "./PublishingSection";

export function BookForm(): React.JSX.Element {
  const {
    currentBook,
    validationErrors,
    isRecognizing,
    updateBookField,
    fetchNextArticle,
    recognizeCurrentBook,
    enrichWithFantlab,
    saveCurrentBook,
  } = useWorkspaceStore();

  const { activeStore } = useSystemStore();
  const isPost2011 = currentBook.template_mode === "post2011";

  // Global Cmd/Ctrl + Enter & Cmd/Ctrl + S save shortcut (v1 parity)
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "Enter" || e.key.toLowerCase() === "s")) {
        e.preventDefault();
        saveCurrentBook(activeStore);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [saveCurrentBook, activeStore]);

  const handleDeriveBarcodeFromIsbn = () => {
    const clean = (currentBook.isbn || "").replace(/\D/g, "");
    if (clean.length === 13) {
      updateBookField("barcode", clean);
    }
  };

  return (
    <div className="rounded-3xl border border-slate-800 bg-slate-900/90 p-6 shadow-2xl space-y-6">
      {/* Top Form Header: Era Status + AI Recognition */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-base font-bold text-white">📝 Карточка книги Ozon</h2>
          <span
            className={`rounded-full px-3 py-1 text-xs font-bold border ${
              isPost2011
                ? "bg-blue-950/70 border-blue-700/70 text-blue-300"
                : "bg-amber-950/70 border-amber-700/70 text-amber-300"
            }`}
          >
            {isPost2011 ? "С 2011 г. (86 колонок — ISBN обязателен)" : "До 2011 г. (81 колонка — Букинистика)"}
          </span>
        </div>

        <button
          type="button"
          onClick={() => recognizeCurrentBook()}
          disabled={isRecognizing}
          className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-indigo-600 to-purple-600 px-4 py-2 text-xs font-bold text-white shadow-lg hover:from-indigo-500 hover:to-purple-500 active:scale-95 disabled:opacity-50 transition"
        >
          <span>{isRecognizing ? "⏳" : "🤖"}</span>
          <span>{isRecognizing ? "Распознавание AI..." : "Распознать по фото (Gemini + FantLab)"}</span>
        </button>
      </div>

      {/* 2-Column Main Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* LEFT COLUMN */}
        <div className="space-y-6">
          {/* SECTION 1: IDENTIFICATION */}
          <div className="space-y-3">
            <h3 className="text-xs font-bold text-amber-400 uppercase tracking-wider">
              1. Идентификация и название
            </h3>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-xs font-medium text-slate-300">
                    Артикул (SKU): <span className="text-rose-400">*</span>
                  </label>
                  <button
                    type="button"
                    onClick={() => fetchNextArticle()}
                    className="text-[10px] text-amber-400 hover:text-amber-300 font-semibold"
                  >
                    🎲 Авто (+1)
                  </button>
                </div>
                <input
                  type="text"
                  value={currentBook.article}
                  onChange={(e) => updateBookField("article", e.target.value)}
                  placeholder="DP-B-03098"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-mono font-bold text-emerald-400 focus:border-amber-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Место хранения (полка):
                </label>
                <input
                  type="text"
                  value={currentBook.storage_location}
                  onChange={(e) => updateBookField("storage_location", e.target.value)}
                  placeholder="Напр.: Шкаф 2 / А-14"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-mono text-amber-300 focus:border-amber-500 focus:outline-none"
                />
              </div>
            </div>

            {/* Barcode EAN-13 */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-medium text-slate-300">Штрихкод (EAN-13):</label>
                <div className="flex items-center gap-2 text-[10px]">
                  <button
                    type="button"
                    onClick={() =>
                      updateBookField("barcode", generateEan13FromArticle(currentBook.article))
                    }
                    className="text-emerald-400 hover:text-emerald-300 font-semibold"
                  >
                    ⚡ Ген. EAN-13
                  </button>
                  <span className="text-slate-600">|</span>
                  <button
                    type="button"
                    onClick={handleDeriveBarcodeFromIsbn}
                    className="text-amber-400 hover:text-amber-300 font-semibold"
                  >
                    Из ISBN
                  </button>
                </div>
              </div>
              <input
                type="text"
                value={currentBook.barcode}
                onChange={(e) => updateBookField("barcode", e.target.value)}
                placeholder="2978470000012"
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-mono text-white focus:border-amber-500 focus:outline-none"
              />
            </div>

            {/* ISBN */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-medium text-slate-300">
                  ISBN: {isPost2011 && <span className="text-rose-400">*</span>}
                </label>
                <button
                  type="button"
                  onClick={() => updateBookField("isbn", "978-5-0000-0000-0")}
                  className="text-[10px] text-amber-400 hover:text-amber-300"
                >
                  Заглушка СССР (до 1987)
                </button>
              </div>
              <input
                type="text"
                value={currentBook.isbn}
                onChange={(e) => updateBookField("isbn", e.target.value)}
                placeholder={isPost2011 ? "978-5-..." : "Необязательно до 2011 г."}
                className={`w-full rounded-xl border bg-slate-950 px-3 py-2 text-xs font-mono text-white focus:outline-none ${
                  validationErrors.isbn ? "border-rose-500" : "border-slate-700 focus:border-amber-500"
                }`}
              />
            </div>

            {/* Title + Manual FantLab Enrichment */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-medium text-slate-300">
                  Точное название книги (без автора): <span className="text-rose-400">*</span>
                </label>
                <button
                  type="button"
                  onClick={() => enrichWithFantlab()}
                  disabled={isRecognizing}
                  className="text-[10px] text-cyan-400 hover:text-cyan-300 bg-cyan-950/50 border border-cyan-800/60 px-2 py-0.5 rounded-lg"
                >
                  🌐 Сверить с базой FantLab
                </button>
              </div>
              <input
                type="text"
                value={currentBook.title}
                onChange={(e) => updateBookField("title", e.target.value)}
                placeholder="например: Всадник без головы"
                className={`w-full rounded-xl border bg-slate-950 px-3.5 py-2 text-sm font-semibold text-white focus:outline-none ${
                  validationErrors.title ? "border-rose-500" : "border-slate-700 focus:border-amber-500"
                }`}
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Оригинальное название (для переводных изданий):
              </label>
              <input
                type="text"
                value={currentBook.original_title}
                onChange={(e) => updateBookField("original_title", e.target.value)}
                placeholder="например: The Headless Horseman"
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white focus:border-amber-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">
                Серия книги (если есть):
              </label>
              <input
                type="text"
                value={currentBook.series}
                onChange={(e) => updateBookField("series", e.target.value)}
                placeholder="например: Библиотека приключений, ЖЗЛ"
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white focus:border-amber-500 focus:outline-none"
              />
            </div>
          </div>

          {/* SECTION 2: AUTHORS */}
          <div className="space-y-3 pt-3 border-t border-slate-800">
            <h3 className="text-xs font-bold text-amber-400 uppercase tracking-wider">
              2. Авторство книги
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Автор на обложке: <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  value={currentBook.author_cover}
                  onChange={(e) => updateBookField("author_cover", e.target.value)}
                  placeholder="Майн Рид"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white focus:border-amber-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  Автор по паспорту (ФИО): <span className="text-rose-400">*</span>
                </label>
                <input
                  type="text"
                  value={currentBook.author}
                  onChange={(e) => updateBookField("author", e.target.value)}
                  placeholder="Рид Томас Майн"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white focus:border-amber-500 focus:outline-none"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Иллюстратор:</label>
                <input
                  type="text"
                  value={currentBook.illustrator}
                  onChange={(e) => updateBookField("illustrator", e.target.value)}
                  placeholder="Художник"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-white focus:border-amber-500 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-xs text-slate-400 mb-1">Переводчик:</label>
                <input
                  type="text"
                  value={currentBook.translator}
                  onChange={(e) => updateBookField("translator", e.target.value)}
                  placeholder="Перевод с языка"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-white focus:border-amber-500 focus:outline-none"
                />
              </div>
            </div>
          </div>

          {/* SECTION 3 */}
          <PublishingSection />
        </div>

        {/* RIGHT COLUMN */}
        <BookFormRightCol />
      </div>
    </div>
  );
}
