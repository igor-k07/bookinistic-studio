/**
 * SettingsModal — Unified Settings, API Keys Status, Storage Cleanup, Mobile QR (Wi-Fi + Tunnel), and Memos.
 */

import React, { useState, useEffect } from "react";
import QRCode from "qrcode";
import { apiRequest } from "../../api/client";
import { useSystemStore } from "../../store/systemStore";

export type SettingsTabKey = "storage" | "mobile" | "keys" | "memos";

interface Props {
  isOpen: boolean;
  initialTab?: SettingsTabKey;
  onClose: () => void;
}

interface KeyStatus {
  configured: boolean;
  masked: string;
}

export function SettingsModal({
  isOpen,
  initialTab = "storage",
  onClose,
}: Props): React.JSX.Element | null {
  const [activeTab, setActiveTab] = useState<SettingsTabKey>(initialTab);
  const [qrMode, setQrMode] = useState<"lan" | "tunnel">("lan");
  const [qrDataUrl, setQrDataUrl] = useState<string>("");
  const [isCleaning, setIsCleaning] = useState(false);
  const [cleanResult, setCleanResult] = useState<string | null>(null);
  const [isRotating, setIsRotating] = useState(false);
  const [isRestartingTunnel, setIsRestartingTunnel] = useState(false);
  const [keysStatus, setKeysStatus] = useState<Record<string, KeyStatus> | null>(null);

  const { tunnelUrl, localUrl, mobileToken, rotateMobileToken, restartTunnel } = useSystemStore();

  useEffect(() => {
    if (isOpen) {
      setActiveTab(initialTab);
      setQrMode(tunnelUrl ? "tunnel" : "lan");
      apiRequest<Record<string, unknown>>("/api/system/keys")
        .then((res) => {
          setKeysStatus({
            gemini: (res.gemini_api_key as KeyStatus) || { configured: false, masked: "" },
            ozon: (res.ozon_api_key as KeyStatus) || { configured: false, masked: "" },
            s3: (res.s3_secret_key as KeyStatus) || { configured: false, masked: "" },
          });
        })
        .catch(() => {});
    }
  }, [isOpen, initialTab, tunnelUrl]);

  const activeBaseUrl =
    qrMode === "tunnel" && tunnelUrl
      ? tunnelUrl
      : localUrl || tunnelUrl || window.location.origin;

  const mobileConnectUrl = `${activeBaseUrl}/mobile?token=${encodeURIComponent(mobileToken || "")}`;

  useEffect(() => {
    if (isOpen && activeTab === "mobile") {
      QRCode.toDataURL(mobileConnectUrl, { width: 230, margin: 1 })
        .then(setQrDataUrl)
        .catch((err) => console.error("QR generation error:", err));
    }
  }, [isOpen, activeTab, mobileConnectUrl]);

  const handleCleanupStorage = async () => {
    if (!confirm("Завершить текущую сессию и удалить временные исходники?")) return;
    setIsCleaning(true);
    setCleanResult(null);
    try {
      const res = await apiRequest<{ cleaned_count?: number; bytes_freed?: number }>(
        "/api/system/cleanup?dry_run=false",
        { method: "POST" }
      );
      const count = res.cleaned_count ?? 0;
      const mbFreed = ((res.bytes_freed ?? 0) / (1024 * 1024)).toFixed(1);
      setCleanResult(`Удалено ${count} файлов, освобождено ${mbFreed} МБ`);
    } catch {
      setCleanResult("Ошибка при выполнении очистки хранилища");
    } finally {
      setIsCleaning(false);
    }
  };

  const handleRotateToken = async () => {
    if (!confirm("Сгенерировать новый мобильный токен?")) return;
    setIsRotating(true);
    try {
      await rotateMobileToken();
    } finally {
      setIsRotating(false);
    }
  };

  const handleRestartTunnel = async () => {
    setIsRestartingTunnel(true);
    try {
      await restartTunnel();
    } finally {
      setIsRestartingTunnel(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-6">
      <div className="flex h-full max-h-[85vh] w-full max-w-3xl flex-col rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl overflow-hidden">
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-950 px-6">
          <span className="text-base font-bold text-white">⚙️ Настройки и подключение телефона</span>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg bg-slate-800 p-1.5 text-slate-400 hover:bg-slate-700 hover:text-white"
          >
            ✕
          </button>
        </div>

        <div className="flex border-b border-slate-800 bg-slate-900/60 px-6 pt-2 gap-1">
          {[
            { id: "mobile", label: "📱 QR для телефона" },
            { id: "keys", label: "🔑 API Ключи" },
            { id: "storage", label: "💾 Хранилище" },
            { id: "memos", label: "📖 Шорткаты" },
          ].map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setActiveTab(t.id as SettingsTabKey)}
              className={`border-b-2 px-4 py-2.5 text-xs font-semibold transition-colors ${
                activeTab === t.id
                  ? "border-emerald-500 text-emerald-400"
                  : "border-transparent text-slate-400 hover:text-slate-200"
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {activeTab === "mobile" && (
            <div className="flex flex-col items-center gap-4 text-center">
              <div className="flex rounded-xl border border-slate-700 bg-slate-950 p-1 text-xs">
                <button
                  type="button"
                  onClick={() => setQrMode("lan")}
                  className={`rounded-lg px-3 py-1.5 font-semibold transition ${
                    qrMode === "lan" ? "bg-amber-600 text-white" : "text-slate-400 hover:text-white"
                  }`}
                >
                  📶 Локальный Wi-Fi (LAN)
                </button>
                <button
                  type="button"
                  onClick={() => setQrMode("tunnel")}
                  className={`rounded-lg px-3 py-1.5 font-semibold transition ${
                    qrMode === "tunnel"
                      ? "bg-emerald-600 text-white"
                      : "text-slate-400 hover:text-white"
                  }`}
                >
                  ☁️ Cloudflare Tunnel {tunnelUrl ? "🟢" : "🔴"}
                </button>
              </div>

              {qrDataUrl ? (
                <div className="rounded-2xl border-4 border-emerald-500/40 bg-white p-3 shadow-2xl">
                  <img src={qrDataUrl} alt="Mobile Connect QR" className="h-56 w-56 rounded-lg" />
                </div>
              ) : (
                <div className="flex h-56 w-56 items-center justify-center rounded-2xl border border-slate-800 bg-slate-950 text-xs text-slate-500">
                  Генерация QR...
                </div>
              )}

              <a
                href={mobileConnectUrl}
                target="_blank"
                rel="noreferrer"
                className="font-mono text-xs text-emerald-400 underline break-all max-w-md"
              >
                {mobileConnectUrl}
              </a>

              <div className="flex flex-wrap items-center justify-center gap-2 mt-1">
                <button
                  type="button"
                  onClick={handleRestartTunnel}
                  disabled={isRestartingTunnel}
                  className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 hover:text-white disabled:opacity-50"
                >
                  {isRestartingTunnel ? "⏳ Запуск туннеля..." : "🚀 Перезапустить Cloudflare Tunnel"}
                </button>
                <button
                  type="button"
                  onClick={handleRotateToken}
                  disabled={isRotating}
                  className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:bg-slate-700 hover:text-white disabled:opacity-50"
                >
                  {isRotating ? "Обновление..." : "🔄 Сгенерировать новый токен"}
                </button>
              </div>
            </div>
          )}

          {activeTab === "keys" && (
            <div className="space-y-3 text-xs">
              {[
                { label: "Gemini Vision API", item: keysStatus?.gemini },
                { label: "Ozon Seller API (активный магазин)", item: keysStatus?.ozon },
                { label: "Yandex Object Storage (S3)", item: keysStatus?.s3 },
              ].map(({ label, item }) => (
                <div
                  key={label}
                  className="flex items-center justify-between rounded-xl border border-slate-800 bg-slate-950/60 px-4 py-3"
                >
                  <span className="font-semibold text-slate-200">{label}</span>
                  <span
                    className={`font-mono px-2.5 py-0.5 rounded-full text-[11px] font-bold ${
                      item?.configured
                        ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                        : "bg-rose-950 text-rose-400 border border-rose-800"
                    }`}
                  >
                    {item?.configured ? `✓ ${item.masked}` : "Не настроен"}
                  </span>
                </div>
              ))}
            </div>
          )}

          {activeTab === "storage" && (
            <div className="flex flex-col gap-5">
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 space-y-3">
                <h4 className="text-sm font-semibold text-slate-200">
                  Очистка временных файлов и завершение смены
                </h4>
                <p className="text-xs text-slate-400">
                  Удаляет архивированные временные исходники, сохраняя все готовые книги в `books_vault`.
                </p>
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={handleCleanupStorage}
                    disabled={isCleaning}
                    className="rounded-lg bg-rose-600/90 px-4 py-2 text-xs font-bold text-white hover:bg-rose-500 disabled:opacity-50"
                  >
                    {isCleaning ? "Очистка..." : "🧹 Завершить сессию и очистить кэш"}
                  </button>
                  {cleanResult && <span className="text-xs text-emerald-400">{cleanResult}</span>}
                </div>
              </div>

              <div className="flex flex-wrap gap-2 text-xs">
                {(["ready_tables", "books_vault", "storage"] as const).map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => apiRequest(`/api/system/open-folder?folder=${f}`, { method: "POST" })}
                    className="rounded-xl border border-slate-700 bg-slate-800 px-3 py-2 font-semibold text-slate-200 hover:bg-slate-700"
                  >
                    📂 Открыть {f}
                  </button>
                ))}
              </div>
            </div>
          )}

          {activeTab === "memos" && (
            <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-4 text-xs text-slate-300">
              <h5 className="font-bold text-emerald-400 uppercase tracking-wider text-[11px]">
                Горячие клавиши
              </h5>
              <ul className="mt-2.5 grid grid-cols-2 gap-2 text-slate-400">
                <li><kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-200">1-5</kbd> — Назначить слот фото</li>
                <li><kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-200">Delete</kbd> — Удалить фото из пула</li>
                <li><kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-200">Cmd/Ctrl + Enter</kbd> — Сохранить и в Ozon</li>
                <li><kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-200">Пробел</kbd> — Оригинал в Фото-студии</li>
                <li><kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-200">R / Shift+R</kbd> — Поворот ±90° в студии</li>
                <li><kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-slate-200">Esc</kbd> — Отмена / закрыть окно</li>
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
