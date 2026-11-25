import React, { useEffect, useState } from "react";
import { setSessionToken } from "../api/client";

export default function MobileApp(): React.JSX.Element {
  const [token, setToken] = useState<string | null>(null);

  useEffect(() => {
    // Read session token from URL parameters ?token=...
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get("token");
    if (urlToken) {
      setToken(urlToken);
      setSessionToken(urlToken);
    }
  }, []);

  return (
    <div className="flex h-screen w-screen flex-col bg-slate-950 text-slate-100">
      <header className="flex h-12 items-center justify-between border-b border-slate-800 px-4">
        <span className="font-semibold text-emerald-400">Мобильная Студия</span>
        <span className="text-xs text-slate-400">
          {token ? "Сессия активна" : "Ожидание токена"}
        </span>
      </header>
      <main className="flex flex-1 flex-col items-center justify-center p-4 text-center">
        <p className="text-slate-400">
          Камера и пошаговая каталогизация книг готовы к инициализации.
        </p>
      </main>
    </div>
  );
}

