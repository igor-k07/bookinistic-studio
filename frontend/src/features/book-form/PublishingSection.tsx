import React from "react";
import { useSystemStore } from "../../store/systemStore";
import { useWorkspaceStore } from "../../store/workspaceStore";
import { BrandAutocomplete } from "./BrandAutocomplete";
import {
  AGE_LIMITS,
  COUNTRIES,
  COVER_TYPES,
  OZON_GENRES,
  PAPER_TYPES,
} from "./ozonCatalogOptions";

function cleanPublisherForBrandMatch(raw: string): string {
  return raw
    .replace(/[«»"']/g, "")
    .replace(/^(издательство|изд-во|ид|ооо|зао|оао)\s+/i, "")
    .trim()
    .toLowerCase();
}

export function PublishingSection(): React.JSX.Element {
  const { currentBook, updateBookField } = useWorkspaceStore();
  const { brands } = useSystemStore();

  const syncBrandWithPublisher = (pub: string) => {
    const cleaned = cleanPublisherForBrandMatch(pub);
    if (!cleaned) return;
    const match = brands.find((b) => b.trim().toLowerCase() === cleaned);
    updateBookField("brand", match || "Нет бренда");
  };

  return (
    <div className="space-y-3 pt-3 border-t border-slate-800">
      <h3 className="text-xs font-bold text-amber-400 uppercase tracking-wider">
        3. Выходные данные и классификация
      </h3>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-slate-300">Издательство:</label>
            <button
              type="button"
              onClick={() => {
                updateBookField("publisher", "Художественная литература");
                syncBrandWithPublisher("Художественная литература");
              }}
              className="text-[10px] text-amber-400 hover:text-amber-300"
            >
              «Худлит»
            </button>
          </div>
          <input
            type="text"
            value={currentBook.publisher}
            onChange={(e) => updateBookField("publisher", e.target.value)}
            onBlur={(e) => {
              if (!currentBook.brand) syncBrandWithPublisher(e.target.value);
            }}
            placeholder="Художественная литература"
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white focus:border-amber-500 focus:outline-none"
          />
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs font-medium text-slate-300">
              Бренд Ozon: <span className="text-rose-400">*</span>
            </label>
            <button
              type="button"
              onClick={() => updateBookField("brand", "Нет бренда")}
              className="text-[10px] text-amber-400 hover:text-amber-300 font-bold"
            >
              «Нет бренда»
            </button>
          </div>
          <BrandAutocomplete
            value={currentBook.brand}
            options={brands}
            onChange={(val) => updateBookField("brand", val)}
          />
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1">Год выпуска:</label>
          <input
            type="number"
            value={currentBook.year ?? ""}
            onChange={(e) =>
              updateBookField("year", e.target.value ? Number(e.target.value) : null)
            }
            placeholder="1984"
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white focus:border-amber-500 focus:outline-none"
          />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1">Страна:</label>
          <select
            value={currentBook.country}
            onChange={(e) => updateBookField("country", e.target.value)}
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-2.5 py-2 text-xs text-white"
          >
            {COUNTRIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1">Страниц:</label>
          <input
            type="number"
            value={currentBook.pages || ""}
            onChange={(e) => updateBookField("pages", Number(e.target.value))}
            placeholder="384"
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white"
          />
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1">Переплет:</label>
          <select
            value={currentBook.cover_type}
            onChange={(e) => updateBookField("cover_type", e.target.value)}
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-2.5 py-2 text-xs text-white"
          >
            {COVER_TYPES.map((ct) => (
              <option key={ct} value={ct}>
                {ct}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1">
            Бумага: <span className="text-rose-400">*</span>
          </label>
          <select
            value={currentBook.paper_type}
            onChange={(e) => updateBookField("paper_type", e.target.value)}
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-2.5 py-2 text-xs text-white"
          >
            {PAPER_TYPES.map((pt) => (
              <option key={pt || "empty"} value={pt}>
                {pt || "-- Выберите тип бумаги --"}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1">
            Жанр Ozon: <span className="text-rose-400">*</span>
          </label>
          <select
            value={currentBook.genre}
            onChange={(e) => updateBookField("genre", e.target.value)}
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-2.5 py-2 text-xs text-white"
          >
            {OZON_GENRES.map((g) => (
              <option key={g} value={g}>
                {g}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1">Возраст Ozon:</label>
          <select
            value={currentBook.age_limit}
            onChange={(e) => updateBookField("age_limit", e.target.value)}
            className="w-full rounded-xl border border-slate-700 bg-slate-950 px-2.5 py-2 text-xs text-white"
          >
            {AGE_LIMITS.map((al) => (
              <option key={al || "none"} value={al}>
                {al || "— Не указан —"}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}
