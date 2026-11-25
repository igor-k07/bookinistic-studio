/**
 * SettingsModal — Unified Settings, Disk Cleanup, Mobile QR with Token Rotation, and Memos.
 *
 * Implements Step 7.4:
 * - Unified modal without duplicate DOM IDs
 * - Disk cleanup action ("🧹 Завершить сессию и очистить кэш")
 * - Live QR code generation for mobile studio with CSRF/CSPRNG token rotation
 * - Operational cheat sheets and shortcuts memo
 */

import React, { useState, useEffect } from "react";
import QRCode from "qrcode";
import { apiRequest } from "../../api/client";
import { useSystemStore } from "../../store/systemStore";

interface Props {
  isOpen: boolean;
  onClose: () => void;
}

type TabKey = "storage" | "mobile" | "memos";

export function SettingsModal({ isOpen, onClose }: Props): React.JSX.Element | null {
  const [activeTab, setActiveTab] = useState<TabKey>("storage");
  const [qrDataUrl, setQrDataUrl] = useState<string>("");
  const [isCleaning, setIsCleaning] = useState(false);
  const [cleanResult, setCleanResult] = useState<string | null>(null);
  const [isRotating, setIsRotating] = useState(false);

  const { tunnelUrl, mobileToken, rotateMobileToken } = useSystemStore();

  // Generate QR code when mobile tab is active
  useEffect(() => {
    if (activeTab === "mobile" && (tunnelUrl || window.location.origin)) {
      const base = tunnelUrl || window.location.origin;
      const mobileUrl = `${base}/mobile?token=${encodeURIComponent(mobileToken || "")}`;
      QRCode.toDataURL(mobileUrl, { width: 240, margin: 1 })
        .then(setQrDataUrl)
        .catch((err) => console.error("QR generation error:", err));
    }
  }, [activeTab, tunnelUrl, mobileToken]);

  const handleCleanupStorage = async () => {
    if (!confirm("Завершить текущую сессию и удалить временные исходники старше 24ч?")) {
      return;
    }
    setIsCleaning(true);
    setCleanResult(null);
    try {
      const res = await apiRequest<{ deleted_count: number; freed_bytes: number }>(
        "/api/system/cleanup-storage",
        {
          method: "POST",
          body: JSON.stringify({ dry_run: false }),
        }
      );
      const mbFreed = (res.freed_bytes / (1024 * 1024)).toFixed(1);
      setCleanResult(`Успешно удалено ${res.deleted_count} файлов, освобождено ${mbFreed} МБ`);
    } catch (err) {
      console.error("Cleanup error:", err);
      setCleanResult("Ошибка при выполнении очистки хранилища");
    } finally {
      setIsCleaning(false);
    }
  };

  const handleRotateToken = async () => {
    if (!confirm("Сгенерировать новый мобильный токен? Все подключенные телефоны потребуют повторного сканирования QR.")) {
      return;
    }
    setIsRotating(true);
    try {
      await rotateMobileToken();
    } catch (err) {
      console.error("Failed to rotate token:", err);
    } finally {
      setIsRotating(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-6">
      <div className="flex h-full max-h-[85vh] w-full max-w-3xl flex-col rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-950 px-6">
          <span className="text-base font-bold text-white">⚙️ Настройки и утилиты</span>
          <button
            onClick={onClose}
            className="rounded-lg bg-slate-800 p-1.5 text-slate-400 hover:bg-slate-700 hover:text-white"
          >
            ✕
          </button>
        </div>

        {/* Tab Navigation */}
        <div className="flex border-b border-slate-800 bg-slate-900/60 px-6 pt-2">
          <button
            onClick={() => setActiveTab("storage")}
            className={`border-b-2 px-4 py-2.5 text-xs font-semibold transition-colors ${
              activeTab === "storage"
                ? "border-emerald-500 text-emerald-400"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            💾 Хранилище и Сессия
          </button>
          <button
            onClick={() => setActiveTab("mobile")}
            className={`border-b-2 px-4 py-2.5 text-xs font-semibold transition-colors ${
              activeTab === "mobile"
                ? "border-emerald-500 text-emerald-400"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            📱 Мобильный доступ (QR)
          </button>
          <button
            onClick={() => setActiveTab("memos")}
            className={`border-b-2 px-4 py-2.5 text-xs font-semibold transition-colors ${
              activeTab === "memos"
                ? "border-emerald-500 text-emerald-400"
                : "border-transparent text-slate-400 hover:text-slate-200"
            }`}
          >
            📖 Памятки и ГОСТ
          </button>
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* TAB 1: Storage & Session */}
          {activeTab === "storage" && (
            <div className="flex flex-col gap-6">
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <h4 className="text-sm font-semibold text-slate-200">
                  Очистка временных файлов и завершение смены
                </h4>
                <p className="mt-1 text-xs text-slate-400">
                  Удаляет промежуточные снимки фотосессий, временный кэш rembg и обработанные исходники, не затрагивая готовые каталогизированные книги в постоянном архиве (books_vault).
                </p>
                <div className="mt-4 flex items-center gap-3">
                  <button
                    onClick={handleCleanupStorage}
                    disabled={isCleaning}
                    className="rounded-lg bg-rose-600/90 px-4 py-2 text-xs font-bold text-white shadow-lg hover:bg-rose-500 active:scale-95 disabled:opacity-50"
                  >
                    {isCleaning ? "Очистка..." : "🧹 Завершить сессию и очистить кэш"}
                  </button>
                  {cleanResult && (
                    <span className="text-xs font-medium text-emerald-400">
                      {cleanResult}
                    </span>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: Mobile QR */}
          {activeTab === "mobile" && (
            <div className="flex flex-col items-center gap-4 text-center">
              <p className="text-xs text-slate-400 max-w-md">
                Отсканируйте камерой смартфона для быстрого подключения мобильного терминала съемки книги.
              </p>

              {qrDataUrl ? (
                <div className="rounded-2xl border-4 border-emerald-500/40 bg-white p-3 shadow-2xl">
                  <img src={qrDataUrl} alt="Mobile Connect QR" className="h-56 w-56 rounded-lg" />
                </div>
              ) : (
                <div className="flex h-56 w-56 items-center justify-center rounded-2xl border border-slate-800 bg-slate-950 text-xs text-slate-500">
                  Генерация QR-кода...
                </div>
              )}

              <div className="flex flex-col items-center gap-2">
                <span className="font-mono text-xs text-slate-300">
                  {tunnelUrl || window.location.origin}/mobile
                </span>
                <span className="font-mono text-[11px] text-slate-500">
                  Токен: {mobileToken ? `${mobileToken.slice(0, 8)}••••••••` : "не задан"}
                </span>
              </div>

              <button
                onClick={handleRotateToken}
                disabled={isRotating}
                className="mt-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 hover:text-white disabled:opacity-50"
              >
                {isRotating ? "Обновление..." : "🔄 Сгенерировать новый токен"}
              </button>
            </div>
          )}

          {/* TAB 3: Memos */}
          {activeTab === "memos" && (
            <div className="flex flex-col gap-5 text-xs text-slate-300">
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <h5 className="font-bold text-emerald-400 uppercase tracking-wider text-[11px]">
                  Горячие клавиши (Desktop)
                </h5>
                <ul className="mt-2.5 grid grid-cols-2 gap-2 text-slate-400">
                  <li><kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-200">1-5</kbd> — Назначить слот фото</li>
                  <li><kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-200">Delete</kbd> — Удалить фото из пула</li>
                  <li><kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-200">Ctrl + S</kbd> — Сохранить книгу</li>
                  <li><kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-200">Пробел</kbd> — Оригинал в студии</li>
                  <li><kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-200">Enter</kbd> — Применить в студии</li>
                  <li><kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-200">Esc</kbd> — Закрыть модальное окно</li>
                </ul>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <h5 className="font-bold text-amber-400 uppercase tracking-wider text-[11px]">
                  Эры Ozon (ADR-4)
                </h5>
                <p className="mt-1 text-slate-400">
                  <span className="font-semibold text-white">До 2011 года (включительно):</span> Букинистический шаблон Ozon. ISBN опционален, обязателен формат издания и сохранность книги.
                </p>
                <p className="mt-1 text-slate-400">
                  <span className="font-semibold text-white">С 2011 года:</span> Современный шаблон Ozon. Обязателен корректный валидный ISBN/EAN-13.
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

