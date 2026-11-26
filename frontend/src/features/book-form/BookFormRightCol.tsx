import React, { useEffect, useState } from "react";
import { apiRequest } from "../../api/client";
import { usePoolStore } from "../../store/poolStore";
import { useSystemStore } from "../../store/systemStore";
import { useWorkspaceStore } from "../../store/workspaceStore";
import { calculateGostDimensionsAndWeight, SOVIET_FORMAT_TABLE } from "./GostPhysicsCalc";
import {
  ANNOTATION_WARNING,
  calcOldPrice,
  CONDITIONS,
  QUICK_FORMATS,
} from "./ozonCatalogOptions";

export function BookFormRightCol(): React.JSX.Element {
  const {
    tabs,
    activeTabId,
    currentBook,
    validationErrors,
    isSaving,
    saveMessage,
    updateBookField,
    updateDimensions,
    saveCurrentBook,
  } = useWorkspaceStore();

  const { assets } = usePoolStore();
  const { activeStore } = useSystemStore();
  const [autoPackageAdder, setAutoPackageAdder] = useState(true);
  const [isUpdatingPics, setIsUpdatingPics] = useState(false);

  const activeTab = tabs.find((t) => t.id === activeTabId);
  const isEditMode = Boolean(activeTab?.is_edit_mode);
  const hasDefectsPhoto = assets.some((a) => a.slot === "mantra_defects");

  // v1 rule: if slot 5 has defect photos, condition cannot be 'Очень хорошая'
  useEffect(() => {
    if (hasDefectsPhoto && currentBook.condition === "Очень хорошая") {
      updateBookField("condition", "Хорошая");
    }
  }, [hasDefectsPhoto, currentBook.condition, updateBookField]);

  const handleSetCondition = (val: string) => {
    if (hasDefectsPhoto && val === "Очень хорошая") {
      updateBookField("condition", "Хорошая");
      return;
    }
    updateBookField("condition", val);
    const shouldWarn = hasDefectsPhoto || val === "Хорошая" || val === "Удовлетворительная";
    const cleanText = currentBook.annotation.replace(ANNOTATION_WARNING, "").trim();
    if (shouldWarn && cleanText && !currentBook.annotation.includes(ANNOTATION_WARNING)) {
      updateBookField("annotation", `${ANNOTATION_WARNING}\n\n${cleanText}`);
    } else if (!shouldWarn && currentBook.annotation.includes(ANNOTATION_WARNING)) {
      updateBookField("annotation", cleanText);
    }
  };

  const handlePriceChange = (val: number) => {
    updateBookField("price", val);
    updateBookField("old_price", calcOldPrice(val));
  };

  const handleApplyGost = (fmtOverride?: string) => {
    const code = fmtOverride || currentBook.format_code || "84×108/32";
    const calc = calculateGostDimensionsAndWeight(
      code,
      currentBook.pages || 200,
      currentBook.cover_type || "Твердый переплет",
      currentBook.paper_type || "Типографская"
    );
    updateDimensions({
      width_mm: calc.width,
      length_mm: calc.length,
      height_mm: calc.height,
      weight_g: calc.weight,
      book_format_code: code,
    });
  };

  const handleUpdateOzonPictures = async () => {
    if (!currentBook.article) return;
    setIsUpdatingPics(true);
    try {
      await apiRequest(`/api/ozon/update-pictures/${encodeURIComponent(currentBook.article)}`, {
        method: "POST",
      });
    } finally {
      setIsUpdatingPics(false);
    }
  };

  const pkgW = (currentBook.dimensions.width_mm || 130) + (autoPackageAdder ? 10 : 0);
  const pkgL = (currentBook.dimensions.length_mm || 205) + (autoPackageAdder ? 10 : 0);
  const pkgH = (currentBook.dimensions.height_mm || 22) + (autoPackageAdder ? 10 : 0);
  const pkgWeight = (currentBook.dimensions.weight_g || 300) + (autoPackageAdder ? 30 : 0);

  return (
    <div className="space-y-6">
      {/* СЕКЦИЯ 4: СОХРАННОСТЬ И ОПИСАНИЕ */}
      <div className="space-y-3">
        <h3 className="text-xs font-bold text-amber-400 uppercase tracking-wider">
          4. Сохранность и описание
        </h3>

        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1.5">
            Сохранность экземпляра (Ozon):
          </label>
          <div className="grid grid-cols-3 gap-2">
            {CONDITIONS.map((c) => {
              const active = currentBook.condition === c.value;
              const disabled = hasDefectsPhoto && c.value === "Очень хорошая";
              return (
                <button
                  key={c.value}
                  type="button"
                  disabled={disabled}
                  onClick={() => handleSetCondition(c.value)}
                  className={`py-2 rounded-xl border text-xs font-semibold transition text-center ${
                    active
                      ? "border-emerald-500 bg-emerald-950/60 text-emerald-300 shadow-sm"
                      : "border-slate-700 bg-slate-950 text-slate-300 hover:border-slate-500"
                  } disabled:opacity-40 disabled:cursor-not-allowed`}
                >
                  {c.label}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="block text-xs font-medium text-slate-300">
              Аннотация книги (пойдет в карточку Ozon):
            </label>
            {hasDefectsPhoto && !currentBook.annotation.includes(ANNOTATION_WARNING) && (
              <button
                type="button"
                onClick={() =>
                  updateBookField("annotation", `${ANNOTATION_WARNING}\n\n${currentBook.annotation}`)
                }
                className="text-[10px] font-semibold text-rose-400 hover:text-rose-300"
              >
                + Вставить плашку о дефектах
              </button>
            )}
          </div>
          <textarea
            rows={4}
            value={currentBook.annotation}
            onChange={(e) => updateBookField("annotation", e.target.value)}
            placeholder="Текст аннотации книги..."
            className="w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-xs text-white focus:border-amber-500 focus:outline-none leading-relaxed"
          />
          <p
            className={`text-[11px] mt-1 flex items-center gap-1.5 ${
              hasDefectsPhoto ? "text-rose-400 font-semibold" : "text-slate-400"
            }`}
          >
            <span>{hasDefectsPhoto ? "⚠️" : "💡"}</span>
            <span>
              Плашка «ВНИМАНИЕ! КНИГА НЕ НОВАЯ...» добавляется автоматически при наличии фото в слоте [5. Только дефекты] или снижении сохранности.
            </span>
          </p>
        </div>
      </div>

      {/* СЕКЦИЯ 5: ЦЕНЫ И ГАБАРИТЫ */}
      <div className="space-y-4 pt-3 border-t border-slate-800">
        <h3 className="text-xs font-bold text-amber-400 uppercase tracking-wider">
          5. Цены и габариты Ozon
        </h3>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-slate-300">
                Цена продажи (₽): <span className="text-rose-400">*</span>
              </label>
              <div className="flex gap-1">
                {[250, 350, 500, 800].map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => handlePriceChange(p)}
                    className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-mono text-emerald-400 hover:bg-slate-700"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
            <input
              type="number"
              value={currentBook.price || ""}
              onChange={(e) => handlePriceChange(Number(e.target.value))}
              placeholder="Введите цену"
              className={`w-full rounded-xl border bg-slate-950 px-3.5 py-2 text-base font-bold font-mono text-emerald-400 focus:outline-none ${
                validationErrors.price ? "border-rose-500" : "border-slate-700 focus:border-amber-500"
              }`}
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">
              Старая цена (+40%, мин +50 ₽):
            </label>
            <input
              type="number"
              value={currentBook.old_price || ""}
              onChange={(e) =>
                updateBookField("old_price", e.target.value ? Number(e.target.value) : null)
              }
              placeholder="не заполнено"
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2 text-base font-mono text-slate-400 focus:border-amber-500 focus:outline-none"
            />
          </div>
        </div>

        {/* ГОСТ Калькулятор + Бейдж упаковки */}
        <div className="rounded-2xl border border-slate-800 bg-slate-950/70 p-3.5 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-1.5">
              <select
                value={currentBook.format_code}
                onChange={(e) => {
                  updateBookField("format_code", e.target.value);
                  handleApplyGost(e.target.value);
                }}
                className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-white"
              >
                {Object.entries(SOVIET_FORMAT_TABLE).map(([code, fmt]) => (
                  <option key={code} value={code}>
                    {fmt.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => handleApplyGost()}
                className="rounded-lg border border-emerald-700/60 bg-emerald-950/60 px-2.5 py-1 text-xs font-semibold text-emerald-300 hover:bg-emerald-900"
              >
                📐 ГОСТ
              </button>
            </div>
            <span className="rounded-xl border border-amber-800/60 bg-amber-950/60 px-2.5 py-1 text-[10px] font-mono font-semibold text-amber-300">
              В Ozon: {pkgW} × {pkgL} × {pkgH} мм · {pkgWeight} г
            </span>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {QUICK_FORMATS.map((qf) => (
              <button
                key={qf.code}
                type="button"
                onClick={() => {
                  updateBookField("format_code", qf.code);
                  updateDimensions({ width_mm: qf.w, length_mm: qf.l, book_format_code: qf.code });
                }}
                className="rounded-lg border border-slate-800 bg-slate-900 px-2 py-0.5 text-[10px] font-mono text-slate-300 hover:border-amber-500/60 hover:text-amber-300"
              >
                {qf.code}
              </button>
            ))}
          </div>

          <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
            <input
              type="checkbox"
              checked={autoPackageAdder}
              onChange={(e) => setAutoPackageAdder(e.target.checked)}
              className="h-4 w-4 rounded border-slate-700 accent-amber-500"
            />
            <span>Прибавлять упаковку к габаритам (+10 мм / +30 г)</span>
          </label>

          <div className="grid grid-cols-4 gap-2">
            {[
              { label: "Ширина (мм)", key: "width_mm", val: currentBook.dimensions.width_mm, pkg: pkgW },
              { label: "Длина (мм)", key: "length_mm", val: currentBook.dimensions.length_mm, pkg: pkgL },
              { label: "Толщина (мм)", key: "height_mm", val: currentBook.dimensions.height_mm, pkg: pkgH },
              { label: "Вес (г)", key: "weight_g", val: currentBook.dimensions.weight_g, pkg: pkgWeight },
            ].map((item) => (
              <div key={item.key}>
                <label className="block text-[10px] text-slate-400 text-center mb-1">{item.label}</label>
                <input
                  type="number"
                  value={item.val}
                  onChange={(e) => updateDimensions({ [item.key]: Number(e.target.value) })}
                  className="w-full rounded-xl border border-slate-700 bg-slate-900 p-2 text-center text-xs font-mono font-semibold text-white"
                />
                <div className="text-[9px] text-amber-400/90 text-center mt-0.5 font-mono">
                  упак: {item.pkg}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Static Ozon Attributes */}
        <div className="flex flex-wrap gap-2 text-[10px] font-mono text-slate-400">
          <span className="rounded-lg bg-slate-950 border border-slate-800 px-2 py-1">ТН ВЭД: 4901990000</span>
          <span className="rounded-lg bg-slate-950 border border-slate-800 px-2 py-1">НДС: Не облагается</span>
          <span className="rounded-lg bg-slate-950 border border-slate-800 px-2 py-1">Тип: Second-hand</span>
        </div>
      </div>

      {/* СТАТУС ВАЛИДАЦИИ И СОХРАНЕНИЯ */}
      {saveMessage && (
        <div
          className={`rounded-xl px-3.5 py-2.5 text-xs font-medium ${
            Object.keys(validationErrors).length > 0
              ? "bg-rose-950/80 border border-rose-700 text-rose-200"
              : "bg-emerald-950/80 border border-emerald-700 text-emerald-200"
          }`}
        >
          {saveMessage}
        </div>
      )}

      {/* ГЛАВНАЯ КНОПКА СОХРАНЕНИЯ */}
      <div className="space-y-2">
        <button
          type="button"
          disabled={isSaving}
          onClick={() => saveCurrentBook(activeStore)}
          className="w-full py-4 px-6 rounded-2xl bg-gradient-to-r from-emerald-600 via-teal-600 to-emerald-700 hover:from-emerald-500 hover:to-teal-500 text-white font-bold text-sm shadow-xl shadow-emerald-600/25 transition flex items-center justify-center gap-2 active:scale-[0.99] disabled:opacity-50"
        >
          <span>{isSaving ? "⏳" : "🚀"}</span>
          <span>
            {isSaving
              ? "Сохранение в БД, Excel и Ozon..."
              : isEditMode
              ? "Сохранить изменения и обновить на Ozon (Cmd + Enter)"
              : "Опубликовать новую книгу на Ozon (Cmd + Enter)"}
          </span>
        </button>

        {isEditMode && (
          <button
            type="button"
            disabled={isUpdatingPics}
            onClick={handleUpdateOzonPictures}
            className="w-full py-2.5 px-4 rounded-xl border border-indigo-700/60 bg-indigo-950/60 text-xs font-semibold text-indigo-300 hover:bg-indigo-900/70 transition disabled:opacity-50"
          >
            {isUpdatingPics ? "⏳ Обновление фото..." : "🔄 Обновить только фото на Ozon"}
          </button>
        )}
      </div>
    </div>
  );
}
