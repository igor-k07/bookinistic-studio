/**
 * ExcelPreviewTable — Embedded v1 Excel & Ozon Preview Table (До 2011 / С 2011 tabs).
 */

import React, { useCallback, useEffect, useState } from "react";
import { apiRequest } from "../../api/client";
import { sseClient } from "../../api/sse";
import { useSystemStore } from "../../store/systemStore";
import { useWorkspaceStore, type BookData } from "../../store/workspaceStore";

export function ExcelPreviewTable(): React.JSX.Element {
  const [mode, setMode] = useState<"pre2011" | "post2011">("pre2011");
  const [books, setBooks] = useState<BookData[]>([]);
  const [preCount, setPreCount] = useState(0);
  const [postCount, setPostCount] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [busyArticle, setBusyArticle] = useState<string | null>(null);

  const { activeStore } = useSystemStore();
  const { reopenBook } = useWorkspaceStore();

  const loadPreview = useCallback(async (targetMode: "pre2011" | "post2011") => {
    setIsLoading(true);
    try {
      const res = await apiRequest<{
        books: BookData[];
        pre2011_count: number;
        post2011_count: number;
      }>(`/api/books/excel-preview?mode=${targetMode}`);
      setBooks(res.books || []);
      setPreCount(res.pre2011_count || 0);
      setPostCount(res.post2011_count || 0);
    } catch (err) {
      console.error("Failed to load Excel preview:", err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPreview(mode);
  }, [mode, activeStore, loadPreview]);

  useEffect(() => {
    const offSaved = sseClient.on("book.saved", () => loadPreview(mode));
    const offOzon = sseClient.on("ozon.status_changed", () => loadPreview(mode));
    return () => {
      offSaved();
      offOzon();
    };
  }, [mode, loadPreview]);

  const handleReopen = async (article: string) => {
    setBusyArticle(article);
    try {
      await reopenBook(article);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } finally {
      setBusyArticle(null);
    }
  };

  const handleUpdateOzonPhotos = async (article: string) => {
    setBusyArticle(article);
    try {
      await apiRequest(`/api/ozon/update-pictures/${encodeURIComponent(article)}`, {
        method: "POST",
      });
      await loadPreview(mode);
    } finally {
      setBusyArticle(null);
    }
  };

  const handleDelete = async (article: string, title: string) => {
    if (
      !confirm(
        `Убрать книгу ${article} («${title}») из таблицы текущей сессии?\n\nКарточка на Ozon и в общей базе НЕ будет удалена.`
      )
    ) {
      return;
    }
    setBusyArticle(article);
    try {
      await apiRequest(`/api/books/excel-row/${encodeURIComponent(article)}`, { method: "DELETE" });
      await loadPreview(mode);
    } finally {
      setBusyArticle(null);
    }
  };

  const handleClearTable = async () => {
    if (!confirm(`Очистить Excel-таблицу (${mode})? Предыдущий файл будет сохранен в ready_tables/backups/.`)) {
      return;
    }
    await apiRequest(`/api/books/clear-excel?mode=${mode}`, { method: "POST" });
    await loadPreview(mode);
  };

  return (
    <section className="rounded-3xl border border-slate-800 bg-slate-900/90 shadow-2xl overflow-hidden">
      {/* Header & Era Tabs */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 bg-slate-950 px-6 py-4">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-sm font-bold text-white uppercase tracking-wide">
            📊 Книги текущей сессии (Excel)
          </h2>

          <div className="flex rounded-xl border border-slate-800 bg-slate-900 p-1 text-xs">
            <button
              type="button"
              onClick={() => setMode("pre2011")}
              className={`rounded-lg px-3 py-1 font-semibold transition ${
                mode === "pre2011"
                  ? "bg-amber-600 text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              До 2011 (81 кол.) · <span className="font-mono">{preCount}</span>
            </button>
            <button
              type="button"
              onClick={() => setMode("post2011")}
              className={`rounded-lg px-3 py-1 font-semibold transition ${
                mode === "post2011"
                  ? "bg-blue-600 text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              С 2011 (86 кол.) · <span className="font-mono">{postCount}</span>
            </button>
          </div>
        </div>

        {/* Toolbar Actions */}
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <button
            type="button"
            onClick={() => loadPreview(mode)}
            className="rounded-xl border border-slate-700 bg-slate-800 px-3 py-1.5 font-semibold text-slate-200 hover:bg-slate-700"
          >
            🔄 Обновить
          </button>
          <button
            type="button"
            onClick={() =>
              apiRequest("/api/system/open-folder?folder=ready_tables", { method: "POST" })
            }
            className="rounded-xl border border-slate-700 bg-slate-800 px-3 py-1.5 font-semibold text-slate-200 hover:bg-slate-700"
          >
            📂 Папка ready_tables
          </button>
          <button
            type="button"
            onClick={() => window.open(`/api/system/excel/download?mode=${mode}`, "_blank")}
            className="rounded-xl bg-emerald-600 px-3.5 py-1.5 font-bold text-white hover:bg-emerald-500 active:scale-95"
          >
            📥 Скачать Excel ({mode === "pre2011" ? "до 2011" : "с 2011"})
          </button>
          <button
            type="button"
            onClick={handleClearTable}
            className="rounded-xl border border-rose-800/70 bg-rose-950/60 px-3 py-1.5 font-semibold text-rose-300 hover:bg-rose-900"
          >
            🗑️ Очистить
          </button>
        </div>
      </div>

      {/* Preview Table */}
      <div className="max-h-[460px] overflow-auto">
        <table className="w-full text-left text-xs text-slate-300">
          <thead className="sticky top-0 bg-slate-950 text-[11px] font-semibold uppercase tracking-wider text-slate-400 border-b border-slate-800">
            <tr>
              <th className="px-3 py-3">№</th>
              <th className="px-3 py-3">Артикул</th>
              <th className="px-3 py-3">Название</th>
              <th className="px-3 py-3">Автор</th>
              <th className="px-3 py-3">Изд-во / Бренд</th>
              <th className="px-3 py-3">Год</th>
              <th className="px-3 py-3">Цена</th>
              <th className="px-3 py-3">Сохранность</th>
              <th className="px-3 py-3">ISBN</th>
              <th className="px-3 py-3">Штрихкод</th>
              <th className="px-3 py-3">Ozon</th>
              <th className="px-3 py-3 text-right">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {isLoading && books.length === 0 ? (
              <tr>
                <td colSpan={12} className="py-10 text-center text-slate-500">
                  Загрузка таблицы...
                </td>
              </tr>
            ) : books.length === 0 ? (
              <tr>
                <td colSpan={12} className="py-10 text-center text-slate-500">
                  В этой таблице пока нет сохранённых книг
                </td>
              </tr>
            ) : (
              books.map((b, idx) => (
                <tr key={b.article} className="hover:bg-slate-800/40 transition-colors">
                  <td className="px-3 py-2.5 font-mono text-slate-500">{idx + 1}</td>
                  <td className="px-3 py-2.5 font-mono font-bold text-emerald-400">{b.article}</td>
                  <td className="px-3 py-2.5 font-medium text-white max-w-[220px] truncate">
                    {b.title || "Без названия"}
                  </td>
                  <td className="px-3 py-2.5 text-slate-400 max-w-[140px] truncate">
                    {b.author_cover || b.author}
                  </td>
                  <td className="px-3 py-2.5 text-slate-400 max-w-[140px] truncate">
                    {b.publisher || b.brand || "—"}
                  </td>
                  <td className="px-3 py-2.5 font-mono">{b.year || "—"}</td>
                  <td className="px-3 py-2.5 font-mono font-bold text-slate-200">
                    {b.price ? `${b.price} ₽` : "—"}
                  </td>
                  <td className="px-3 py-2.5">{b.condition}</td>
                  <td className="px-3 py-2.5 font-mono text-[11px] text-slate-400">
                    {b.isbn || "—"}
                  </td>
                  <td className="px-3 py-2.5 font-mono text-[11px] text-slate-400">
                    {b.barcode || "—"}
                  </td>
                  <td className="px-3 py-2.5">
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold ${
                        b.ozon_sync_status === "PUBLISHED"
                          ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                          : b.ozon_sync_status === "QUEUED" || b.ozon_sync_status === "MODERATION"
                          ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                          : b.ozon_sync_status === "ERROR"
                          ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                          : "bg-slate-800 text-slate-400"
                      }`}
                    >
                      {b.ozon_sync_status || "В базе"}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <div className="flex items-center justify-end gap-1">
                      <button
                        type="button"
                        disabled={busyArticle === b.article}
                        onClick={() => handleReopen(b.article)}
                        title="Открыть в редакторе"
                        className="rounded-lg bg-emerald-600/80 px-2 py-1 text-white hover:bg-emerald-500 disabled:opacity-40"
                      >
                        ✏️
                      </button>
                      <button
                        type="button"
                        disabled={busyArticle === b.article}
                        onClick={() => handleUpdateOzonPhotos(b.article)}
                        title="Обновить фото на Ozon"
                        className="rounded-lg bg-indigo-600/80 px-2 py-1 text-white hover:bg-indigo-500 disabled:opacity-40"
                      >
                        🔄
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          window.open(
                            `/api/system/photos-zip?article=${encodeURIComponent(b.article)}`,
                            "_blank"
                          )
                        }
                        title="Скачать ZIP фото"
                        className="rounded-lg bg-slate-800 px-2 py-1 text-slate-300 hover:bg-slate-700"
                      >
                        📦
                      </button>
                      <button
                        type="button"
                        disabled={busyArticle === b.article}
                        onClick={() => handleDelete(b.article, b.title)}
                        title="Удалить строку"
                        className="rounded-lg bg-rose-950/80 px-2 py-1 text-rose-400 hover:bg-rose-800 hover:text-white disabled:opacity-40"
                      >
                        🗑️
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

