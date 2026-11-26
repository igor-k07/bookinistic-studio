/**
 * CatalogTable — Full-Text FTS5 Catalog Search Modal (2,378+ books) + Ozon Smart S3 Sync.
 */

import React, { useState, useEffect, useRef, useCallback } from "react";
import { apiRequest } from "../../api/client";
import { useSystemStore } from "../../store/systemStore";
import { useWorkspaceStore, type BookData } from "../../store/workspaceStore";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

export function CatalogTable({ isOpen, onClose }: Props): React.JSX.Element | null {
  const [searchQuery, setSearchQuery] = useState("");
  const [books, setBooks] = useState<BookData[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [importProgress, setImportProgress] = useState<{
    progress: number;
    total: number;
    imported: number;
    updated: number;
    error: string | null;
  } | null>(null);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [reopeningArticle, setReopeningArticle] = useState<string | null>(null);

  const abortControllerRef = useRef<AbortController | null>(null);
  const { reopenBook } = useWorkspaceStore();
  const { activeStore, fetchOzonStatus } = useSystemStore();

  const fetchCatalog = useCallback(async (query: string) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const ac = new AbortController();
    abortControllerRef.current = ac;

    setIsLoading(true);
    try {
      const url = `/api/books/catalog?query=${encodeURIComponent(query.trim())}&limit=50`;
      const res = await apiRequest<{ books: BookData[]; total: number }>(url, {
        signal: ac.signal,
      });
      setBooks(res.books || []);
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
  }, [isOpen, searchQuery, activeStore, fetchCatalog]);

  const handleReopen = async (article: string) => {
    setReopeningArticle(article);
    try {
      await reopenBook(article);
      onClose();
      window.scrollTo({ top: 0, behavior: "smooth" });
    } finally {
      setReopeningArticle(null);
    }
  };

  const handleImportFromOzon = async () => {
    setIsImporting(true);
    setSyncMsg(null);
    setImportProgress({ progress: 0, total: 0, imported: 0, updated: 0, error: null });
    try {
      await apiRequest("/api/ozon/import-catalog", { method: "POST" });
      const poll = async () => {
        const st = await apiRequest<{
          running: boolean;
          progress: number;
          total: number;
          imported: number;
          updated: number;
          error: string | null;
          done: boolean;
        }>("/api/ozon/import-status");
        setImportProgress({
          progress: st.progress,
          total: st.total,
          imported: st.imported,
          updated: st.updated,
          error: st.error,
        });
        if (st.running) {
          window.setTimeout(poll, 1200);
        } else {
          setIsImporting(false);
          if (st.error) {
            setSyncMsg(`Ошибка выгрузки: ${st.error}`);
          } else {
            setSyncMsg(`Готово! Новых: ${st.imported}, обновлено: ${st.updated}`);
            fetchCatalog(searchQuery);
            fetchOzonStatus();
          }
        }
      };
      window.setTimeout(poll, 800);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setSyncMsg(`Ошибка старта выгрузки: ${msg}`);
      setIsImporting(false);
    }
  };

  const handleSmartS3Sync = async () => {
    setIsSyncing(true);
    setSyncMsg(null);
    try {
      const res = await apiRequest<{ total_updated?: number; status?: string }>(
        "/api/ozon/sync/smart-s3",
        {
          method: "POST",
          body: JSON.stringify({ store_id: activeStore, batch_size: 50 }),
        }
      );
      setSyncMsg(`Smart S3 Sync завершён (обновлено: ${res.total_updated ?? 0})`);
      fetchCatalog(searchQuery);
      fetchOzonStatus();
    } catch (err) {
      console.error("Smart S3 sync error:", err);
      setSyncMsg("Ошибка синхронизации с Ozon");
    } finally {
      setIsSyncing(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-6">
      <div className="flex h-full max-h-[90vh] w-full max-w-6xl flex-col rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl overflow-hidden">
        <div className="flex h-16 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-950 px-6">
          <div className="flex items-center gap-3">
            <span className="text-base font-bold text-white">📚 База книг (SQLite FTS5)</span>
            <span className="rounded-full bg-slate-800 px-2.5 py-0.5 text-xs font-mono text-amber-300">
              Найдено: {books.length}
            </span>
            {syncMsg && <span className="text-xs text-emerald-400 font-medium">{syncMsg}</span>}
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleImportFromOzon}
              disabled={isImporting}
              className="rounded-xl bg-emerald-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-emerald-500 active:scale-95 disabled:opacity-50"
            >
              {isImporting
                ? `⏳ Выгрузка Ozon (${importProgress?.progress || 0}/${importProgress?.total || "?"})...`
                : "📥 Выгрузить карточки с Ozon"}
            </button>
            <button
              type="button"
              onClick={handleSmartS3Sync}
              disabled={isSyncing}
              className="rounded-xl border border-indigo-700/70 bg-indigo-950/70 px-3 py-1.5 text-xs font-semibold text-indigo-300 hover:bg-indigo-900 disabled:opacity-50"
            >
              {isSyncing ? "⏳ Синхронизация..." : "🔄 Smart S3 Sync"}
            </button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg bg-slate-800 p-1.5 text-slate-400 hover:bg-slate-700 hover:text-white ml-2"
            >
              ✕
            </button>
          </div>
        </div>

        <div className="border-b border-slate-800 bg-slate-900/50 p-4">
          <div className="relative">
            <span className="absolute left-3.5 top-2.5 text-slate-400">🔍</span>
            <input
              type="text"
              autoFocus
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Поиск по артикулу (DP-B-...), названию, автору, издательству или ISBN..."
              className="w-full rounded-xl border border-slate-700 bg-slate-950 py-2.5 pl-10 pr-4 text-sm text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
            />
            {isLoading && (
              <span className="absolute right-4 top-3 text-xs text-slate-400 animate-pulse">
                Поиск...
              </span>
            )}
          </div>
        </div>

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
                    <td className="px-4 py-3 font-mono font-bold text-emerald-400">{b.article}</td>
                    <td className="px-4 py-3 font-medium text-white max-w-xs truncate">
                      {b.title || "Без названия"}
                    </td>
                    <td className="px-4 py-3 text-slate-400 max-w-[140px] truncate">
                      {b.author || "не указан"}
                    </td>
                    <td className="px-4 py-3 font-mono">{b.year || "—"}</td>
                    <td className="px-4 py-3 font-mono font-semibold text-slate-200">
                      {b.price ? `${b.price} ₽` : "—"}
                    </td>
                    <td className="px-4 py-3 font-mono text-amber-300">
                      {b.storage_location || "—"}
                    </td>
                    <td className="px-4 py-3">
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
                    <td className="px-4 py-3 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          type="button"
                          onClick={() => handleReopen(b.article)}
                          disabled={reopeningArticle === b.article}
                          className="rounded-lg bg-emerald-600/80 px-2.5 py-1 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
                        >
                          {reopeningArticle === b.article ? "Открытие..." : "✏️ Открыть"}
                        </button>
                        <button
                          type="button"
                          onClick={() =>
                            window.open(
                              `/api/system/photos-zip?article=${encodeURIComponent(b.article)}`,
                              "_blank"
                            )
                          }
                          className="rounded-lg bg-slate-800 px-2 py-1 text-slate-300 hover:bg-slate-700"
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
