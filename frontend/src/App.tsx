import React, { useEffect, useState } from "react";
import { apiRequest } from "./api/client";
import { sseClient } from "./api/sse";

export default function App(): React.JSX.Element {
  const [bootstrapData, setBootstrapData] = useState<{
    active_store?: string;
    brands?: string[];
    mobile_token?: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Fetch bootstrap state on mount
    apiRequest<{
      active_store: string;
      brands: string[];
      mobile_token: string;
    }>("/api/bootstrap")
      .then((data) => setBootstrapData(data))
      .catch((err) => setError(err.message));

    // Connect SSE listener
    sseClient.connect();

    return () => {
      sseClient.disconnect();
    };
  }, []);

  return (
    <div className="flex h-screen w-screen flex-col bg-slate-900 text-slate-100">
      <header className="flex h-14 items-center justify-between border-b border-slate-800 px-6">
        <div className="flex items-center gap-3">
          <span className="text-xl font-bold tracking-tight text-white">
            Bookinistic Studio <span className="text-emerald-500">2.0</span>
          </span>
          {bootstrapData?.active_store && (
            <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
              Магазин: {bootstrapData.active_store}
            </span>
          )}
        </div>
        <div className="flex items-center gap-4 text-sm text-slate-400">
          {error && <span className="text-red-400">{error}</span>}
          <span>Статус: Подключено</span>
        </div>
      </header>
      <main className="flex flex-1 items-center justify-center p-6">
        <div className="text-center">
          <h2 className="text-2xl font-semibold">Рабочая область Desktop</h2>
          <p className="mt-2 text-slate-400">
            Инициализация ядра завершена. Готово к загрузке вкладок и пула фотографий.
          </p>
        </div>
      </main>
    </div>
  );
}

