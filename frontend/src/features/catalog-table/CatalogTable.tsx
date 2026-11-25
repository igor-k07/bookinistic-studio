/**
 * CatalogTable — Fast FTS5 Catalog Search, Outbox Status Badges, and Book Re-opening.
 *
 * Implements Step 7.4:
 * - Debounced FTS5 search with AbortController cancellation
 * - Live Ozon Outbox / Sync status indicators
 * - Re-open book into active workspace tab (POST /api/books/reopen)
 * - Single-click Excel and ZIP photo export downloads
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import { apiRequest } from "../../api/client";
import { useWorkspaceStore, type BookData } from "../../store/workspaceStore";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export function CatalogTable({ isOpen, onClose }: Props): React.JSX.Element | null {
  const [searchQuery, setSearchQuery] = useState("");
  const [books, setBooks] = useState<BookData[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [reopeningArticle, setReopeningArticle] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const { reopenBook } = useWorkspaceStore();

  const fetchCatalog = useCallback(async (query: string) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const ac = new AbortController();
    abortControllerRef.current = ac;

    setIsLoading(true);
    try {
      const url = query.trim()
        ? `/api/catalog/search?q=${encodeURIComponent(query)}&limit=50`
        : "/api/catalog/search?limit=50";

      const res = await apiRequest<{ items: BookData[] }>(url, {
        signal: ac.signal,
      });
      setBooks(res.items || []);
    } catch (err: unknown) {
      if ((err as Error).name !== "AbortError") {
        console.error("Failed to load catalog:", err);
      }
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      fetchCatalog(searchQuery);
    }
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [isOpen, searchQuery, fetchCatalog]);

  const handleReopen = async (article: string) => {
    setReopeningArticle(article);
    try {
      await reopenBook(article);
      onClose();
    } catch (err) {
      console.error("Failed to reopen book:", err);
    } finally {
      setReopeningArticle(null);
    }
  };

  const handleDownloadExcel = (mode: "pre2011" | "post2011") => {
    window.open(`/api/export/excel?mode=${mode}`, "_blank");
  };

  const handleDownloadZip = (article: string) => {
    window.open(`/api/assets/export-zip?article=${encodeURIComponent(article)}`, "_blank");
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-6">
      <div className="flex h-full max-h-[90vh] w-full max-w-6xl flex-col rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl overflow-hidden">
        {/* Header Bar */}
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-950 px-6">
          <div className="flex items-center gap-3">
            <span className="text-base font-bold text-white">📚 Каталог книг</span>
            <span className="rounded-full bg-slate-800 px-2.5 py-0.5 text-xs font-mono text-slate-300">
              {books.length} записей
            </span>
          </div>

          {/* Quick Exports */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => handleDownloadExcel("pre2011")}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700"
            >
              📥 Excel До 2011
            </button>
            <button
              onClick={() => handleDownloadExcel("post2011")}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700"
            >
              📥 Excel С 2011
            </button>
            <button
              onClick={onClose}
              className="rounded-lg bg-slate-800 p-1.5 text-slate-400 hover:bg-slate-700 hover:text-white ml-2"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Search Bar */}
        <div className="border-b border-slate-800 bg-slate-900/50 p-4">
          <div className="relative">
            <span className="absolute left-3.5 top-2.5 text-slate-400">🔍</span>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Быстрый FTS5 поиск по артикулу, названию, автору или издательству..."
              className="w-full rounded-xl border border-slate-700 bg-slate-950 py-2.5 pl-10 pr-4 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
            />
            {isLoading && (
              <span className="absolute right-4 top-3 text-xs text-slate-400 animate-pulse">
                Поиск...
              </span>
            )}
          </div>
        </div>

        {/* Books Table */}
        <div className="flex-1 overflow-auto">
          <table className="w-full text-left text-xs text-slate-300">
            <thead className="sticky top-0 bg-slate-950 text-[11px] font-semibold uppercase tracking-wider text-slate-400 border-b border-slate-800">
              <tr>
                <th className="px-4 py-3">Артикул</th>
                <th className="px-4 py-3">Название</th>
                <th className="px-4 py-3">Автор</th>
                <th className="px-4 py-3">Год</th>
                <th className="px-4 py-3">Цена</th>
                <th className="px-4 py-3">Место</th>
                <th className="px-4 py-3">Ozon Статус</th>
                <th className="px-4 py-3 text-right">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {books.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-slate-500">
                    {isLoading ? "Загрузка каталога..." : "Книги не найдены"}
                  </td>
                </tr>
              ) : (
                books.map((b) => (
                  <tr key={b.article} className="hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3 font-mono font-bold text-emerald-400">
                      {b.article}
                    </td>
                    <td className="px-4 py-3 font-medium text-white max-w-xs truncate">
                      {b.title || "Без названия"}
                    </td>
                    <td className="px-4 py-3 text-slate-400 max-w-[140px] truncate">
                      {b.author || "не указан"}
                    </td>
                    <td className="px-4 py-3">{b.year || "—"}</td>
                    <td className="px-4 py-3 font-semibold text-slate-200">
                      {b.price ? `${b.price} ₽` : "—"}
                    </td>
                    <td className="px-4 py-3 font-mono text-amber-300">
                      {b.storage_location || "—"}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-bold ${
                          b.ozon_sync_status === "SUCCESS"
                            ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                            : b.ozon_sync_status === "PENDING"
                            ? "bg-amber-500/20 text-amber-400 border border-amber-500/30"
                            : b.ozon_sync_status === "ERROR"
                            ? "bg-rose-500/20 text-rose-400 border border-rose-500/30"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {b.ozon_sync_status || "Не выгружено"}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => handleReopen(b.article)}
                          disabled={reopeningArticle === b.article}
                          className="rounded-lg bg-emerald-600/80 px-2.5 py-1 text-xs font-semibold text-white hover:bg-emerald-500 active:scale-95 disabled:opacity-50"
                        >
                          {reopeningArticle === b.article ? "Открытие..." : "Редактировать"}
                        </button>
                        <button
                          onClick={() => handleDownloadZip(b.article)}
                          title="Скачать ZIP архив с фото"
                          className="rounded-lg bg-slate-800 p-1 text-slate-300 hover:bg-slate-700"
                        >
                          📦 ZIP
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

