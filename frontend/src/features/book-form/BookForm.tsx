import React from "react";
import { useSystemStore } from "../../store/systemStore";
import { useWorkspaceStore } from "../../store/workspaceStore";
import { BrandAutocomplete } from "./BrandAutocomplete";
import { calculateGostDimensionsAndWeight, SOVIET_FORMAT_TABLE } from "./GostPhysicsCalc";

export function BookForm(): React.JSX.Element {
  const { currentBook, updateBookField, updateDimensions, validationErrors, isSaving, saveMessage, saveCurrentBook } =
    useWorkspaceStore();
  const { brands } = useSystemStore();

  const isPost2011 = currentBook.template_mode === "post2011";

  const handleApplyGostPhysics = () => {
    const calc = calculateGostDimensionsAndWeight(
      currentBook.format_code,
      currentBook.pages,
      currentBook.cover_type,
      currentBook.paper_type
    );
    updateDimensions({
      width_mm: calc.width,
      length_mm: calc.length,
      height_mm: calc.height,
      weight_g: calc.weight,
      book_format_code: currentBook.format_code,
    });
  };

  return (
    <div className="flex flex-col gap-5 rounded-2xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-md">
      {/* Top Header: Title, Era Badge, Single Save Button */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <span className="font-mono text-sm font-bold text-emerald-400">
            {currentBook.article || "Новый черновик"}
          </span>
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
              isPost2011
                ? "bg-purple-900/60 text-purple-300 border border-purple-700/50"
                : "bg-amber-900/60 text-amber-300 border border-amber-700/50"
            }`}
          >
            {isPost2011 ? "Современная книга (с 2011)" : "Букинистика (до 2011)"}
          </span>
          {currentBook.ozon_sync_status && (
            <span className="rounded bg-blue-900/50 px-2 py-0.5 text-xs text-blue-300">
              Ozon: {currentBook.ozon_sync_status}
            </span>
          )}
        </div>

        <button
          disabled={isSaving}
          onClick={saveCurrentBook}
          className="flex items-center gap-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-bold text-white shadow-lg shadow-emerald-900/30 transition-all hover:bg-emerald-500 active:scale-95 disabled:opacity-50"
        >
          {isSaving ? "Сохранение..." : "💾 Сохранить"}
        </button>
      </div>

      {saveMessage && (
        <div className="rounded-lg bg-emerald-950/80 border border-emerald-800/80 p-3 text-xs text-emerald-300">
          {saveMessage}
        </div>
      )}

      {/* 1. Basic Information */}
      <section className="flex flex-col gap-3">
        <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
          1. Основные сведения
        </h4>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div className="md:col-span-2">
            <label className="mb-1 block text-xs font-medium text-slate-300">Название книги *</label>
            <input
              type="text"
              value={currentBook.title}
              onChange={(e) => updateBookField("title", e.target.value)}
              placeholder="Полное название издания"
              className={`w-full rounded-lg border bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 ${
                validationErrors.title
                  ? "border-rose-500 focus:ring-rose-500/50"
                  : "border-slate-700 focus:border-emerald-500 focus:ring-emerald-500/30"
              }`}
            />
            {validationErrors.title && (
              <span className="mt-1 block text-xs text-rose-400">{validationErrors.title}</span>
            )}
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Автор(ы) *</label>
            <input
              type="text"
              value={currentBook.author}
              onChange={(e) => updateBookField("author", e.target.value)}
              placeholder="Фамилия Имя"
              className={`w-full rounded-lg border bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 ${
                validationErrors.author
                  ? "border-rose-500 focus:ring-rose-500/50"
                  : "border-slate-700 focus:border-emerald-500 focus:ring-emerald-500/30"
              }`}
            />
            {validationErrors.author && (
              <span className="mt-1 block text-xs text-rose-400">{validationErrors.author}</span>
            )}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Год издания *</label>
            <input
              type="number"
              value={currentBook.year ?? ""}
              onChange={(e) =>
                updateBookField("year", e.target.value ? parseInt(e.target.value, 10) : null)
              }
              placeholder="1984"
              className={`w-full rounded-lg border bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 ${
                validationErrors.year
                  ? "border-rose-500 focus:ring-rose-500/50"
                  : "border-slate-700 focus:border-emerald-500 focus:ring-emerald-500/30"
              }`}
            />
            {validationErrors.year && (
              <span className="mt-1 block text-xs text-rose-400">{validationErrors.year}</span>
            )}
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Цена (руб.) *</label>
            <input
              type="number"
              value={currentBook.price || ""}
              onChange={(e) => updateBookField("price", parseFloat(e.target.value) || 0)}
              placeholder="500"
              className={`w-full rounded-lg border bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 ${
                validationErrors.price
                  ? "border-rose-500 focus:ring-rose-500/50"
                  : "border-slate-700 focus:border-emerald-500 focus:ring-emerald-500/30"
              }`}
            />
            {validationErrors.price && (
              <span className="mt-1 block text-xs text-rose-400">{validationErrors.price}</span>
            )}
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Цена до скидки</label>
            <input
              type="number"
              value={currentBook.old_price ?? ""}
              onChange={(e) =>
                updateBookField("old_price", e.target.value ? parseFloat(e.target.value) : null)
              }
              placeholder="750"
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Складское место</label>
            <input
              type="text"
              value={currentBook.storage_location}
              onChange={(e) => updateBookField("storage_location", e.target.value)}
              placeholder="Полка / Коробка"
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
            />
          </div>
        </div>
      </section>

      {/* 2. Publishing & Identifiers */}
      <section className="flex flex-col gap-3 border-t border-slate-800/80 pt-4">
        <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
          2. Издание и идентификаторы
        </h4>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">
              Издательство / Бренд *
            </label>
            <BrandAutocomplete
              value={currentBook.publisher || currentBook.brand}
              onChange={(val) => {
                updateBookField("publisher", val);
                updateBookField("brand", val);
              }}
              options={brands}
              placeholder="Выберите или введите..."
              error={validationErrors.publisher || validationErrors.brand}
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">
              ISBN {isPost2011 ? "*" : "(для современных)"}
            </label>
            <input
              type="text"
              value={currentBook.isbn}
              onChange={(e) => updateBookField("isbn", e.target.value)}
              placeholder="978-5-..."
              className={`w-full rounded-lg border bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 ${
                validationErrors.isbn
                  ? "border-rose-500 focus:ring-rose-500/50"
                  : "border-slate-700 focus:border-emerald-500 focus:ring-emerald-500/30"
              }`}
            />
            {validationErrors.isbn && (
              <span className="mt-1 block text-xs text-rose-400">{validationErrors.isbn}</span>
            )}
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Штрихкод (EAN-13)</label>
            <input
              type="text"
              value={currentBook.barcode}
              onChange={(e) => updateBookField("barcode", e.target.value)}
              placeholder="460..."
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
            />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Страниц *</label>
            <input
              type="number"
              value={currentBook.pages || ""}
              onChange={(e) => updateBookField("pages", parseInt(e.target.value, 10) || 0)}
              placeholder="320"
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Переплет</label>
            <select
              value={currentBook.cover_type}
              onChange={(e) => updateBookField("cover_type", e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
            >
              <option value="Твердый переплет">Твердый переплет</option>
              <option value="Мягкая обложка">Мягкая обложка</option>
              <option value="Кожаный переплет">Кожаный переплет</option>
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Формат ГОСТ</label>
            <select
              value={currentBook.format_code}
              onChange={(e) => updateBookField("format_code", e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
            >
              {Object.keys(SOVIET_FORMAT_TABLE).map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-300">Тип бумаги</label>
            <select
              value={currentBook.paper_type}
              onChange={(e) => updateBookField("paper_type", e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
            >
              <option value="Типографская">Типографская (65 г/м²)</option>
              <option value="Офсетная">Офсетная (80 г/м²)</option>
              <option value="Мелованная">Мелованная (115 г/м²)</option>
              <option value="Газетная">Газетная (50 г/м²)</option>
            </select>
          </div>
        </div>
      </section>

      {/* 3. Physics & Dimensions */}
      <section className="flex flex-col gap-3 border-t border-slate-800/80 pt-4">
        <div className="flex items-center justify-between">
          <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
            3. Физические габариты и вес (ГОСТ)
          </h4>
          <button
            type="button"
            onClick={handleApplyGostPhysics}
            className="rounded bg-slate-800 px-2 py-1 text-xs font-medium text-emerald-400 hover:bg-slate-700"
          >
            ⚡ Рассчитать по ГОСТ
          </button>
        </div>

        <div className="grid grid-cols-4 gap-3">
          <div>
            <label className="mb-1 block text-xs text-slate-400">Ширина (мм)</label>
            <input
              type="number"
              value={currentBook.dimensions?.width_mm || 130}
              onChange={(e) =>
                updateDimensions({ width_mm: parseInt(e.target.value, 10) || 0 })
              }
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Длина (мм)</label>
            <input
              type="number"
              value={currentBook.dimensions?.length_mm || 200}
              onChange={(e) =>
                updateDimensions({ length_mm: parseInt(e.target.value, 10) || 0 })
              }
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Высота (мм)</label>
            <input
              type="number"
              value={currentBook.dimensions?.height_mm || 15}
              onChange={(e) =>
                updateDimensions({ height_mm: parseInt(e.target.value, 10) || 0 })
              }
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:outline-none"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-400">Вес (г)</label>
            <input
              type="number"
              value={currentBook.dimensions?.weight_g || 250}
              onChange={(e) =>
                updateDimensions({ weight_g: parseInt(e.target.value, 10) || 0 })
              }
              className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:outline-none"
            />
          </div>
        </div>
      </section>

      {/* 4. Condition & Annotation */}
      <section className="flex flex-col gap-3 border-t border-slate-800/80 pt-4">
        <h4 className="text-xs font-bold text-slate-400 uppercase tracking-wider">
          4. Состояние и аннотация
        </h4>
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-300">Сохранность</label>
          <select
            value={currentBook.condition}
            onChange={(e) => updateBookField("condition", e.target.value)}
            className="w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
          >
            <option value="Новая">Новая</option>
            <option value="Отличная">Отличная</option>
            <option value="Хорошая">Хорошая</option>
            <option value="Удовлетворительная">Удовлетворительная</option>
          </select>
        </div>

        <div>
          <label className="mb-1 block text-xs font-medium text-slate-300">Аннотация к книге</label>
          <textarea
            rows={4}
            value={currentBook.annotation}
            onChange={(e) => updateBookField("annotation", e.target.value)}
            placeholder="Описание содержания и особенностей издания..."
            className="w-full rounded-lg border border-slate-700 bg-slate-800 p-3 text-sm text-slate-100 placeholder-slate-500 focus:border-emerald-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/30"
          />
        </div>
      </section>
    </div>
  );
}

