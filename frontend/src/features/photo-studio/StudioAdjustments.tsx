import React, { useState } from "react";
import type { StudioTransformState } from "./HistoryStack";
import { STUDIO_PRESETS, type CropRatio } from "./StudioEngine";

interface Props {
  currentTransform: StudioTransformState;
  cropRatio: CropRatio;
  isAiProcessing: boolean;
  onCropRatioChange: (ratio: CropRatio) => void;
  onRotate: (deg: number) => void;
  onStraighten: (deg: number) => void;
  onFilterChange: (key: keyof StudioTransformState["filters"], val: number) => void;
  onApplyPreset: (presetKey: keyof typeof STUDIO_PRESETS) => void;
  onRunAiRembg: () => void;
  onResetAll: () => void;
}

type StudioTab = "crop" | "adjust" | "styles";

export function StudioAdjustments({
  currentTransform,
  cropRatio,
  isAiProcessing,
  onCropRatioChange,
  onRotate,
  onStraighten,
  onFilterChange,
  onApplyPreset,
  onRunAiRembg,
  onResetAll,
}: Props): React.JSX.Element {
  const [tab, setTab] = useState<StudioTab>("crop");

  return (
    <div className="w-80 shrink-0 border-l border-slate-800 bg-slate-900/95 flex flex-col overflow-hidden">
      {/* 3 v1 Studio Tabs */}
      <div className="grid grid-cols-3 border-b border-slate-800 bg-slate-950/70 p-1.5 gap-1 text-xs">
        {[
          { id: "crop", label: "✂️ Обрезка" },
          { id: "adjust", label: "🎨 Цвет" },
          { id: "styles", label: "✨ Стили" },
        ].map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id as StudioTab)}
            className={`rounded-lg py-1.5 font-semibold transition ${
              tab === t.id
                ? "bg-amber-600 text-white shadow"
                : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-5">
        {/* TAB 1: CROP & STRAIGHTEN */}
        {tab === "crop" && (
          <div className="flex flex-col gap-5">
            <div className="space-y-2">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Пропорции рамки (Ozon 3:4)
              </span>
              <div className="grid grid-cols-2 gap-1.5 text-xs">
                {(
                  [
                    { id: "3:4", label: "3:4 Ozon" },
                    { id: "free", label: "Свободно" },
                    { id: "4:3", label: "4:3 Альбом" },
                    { id: "1:1", label: "1:1 Квадрат" },
                  ] as Array<{ id: CropRatio; label: string }>
                ).map((r) => (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => onCropRatioChange(r.id)}
                    className={`rounded-xl py-2 font-semibold border transition ${
                      cropRatio === r.id
                        ? "border-emerald-500 bg-emerald-950/60 text-emerald-300"
                        : "border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700"
                    }`}
                  >
                    {r.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-2 border-t border-slate-800 pt-4">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Поворот и выравнивание
              </span>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => onRotate(-90)}
                  className="flex-1 rounded-xl bg-slate-800 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
                >
                  ↺ -90°
                </button>
                <button
                  type="button"
                  onClick={() => onRotate(90)}
                  className="flex-1 rounded-xl bg-slate-800 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
                >
                  ↻ +90°
                </button>
                <button
                  type="button"
                  onClick={() => onStraighten(0)}
                  className="rounded-xl bg-slate-800 px-3 py-2 text-xs text-slate-400 hover:text-white"
                >
                  0°
                </button>
              </div>

              <div className="mt-2 flex flex-col gap-1.5">
                <div className="flex justify-between text-[11px] text-slate-400">
                  <span>Линейка наклона (-45°..+45°)</span>
                  <button
                    type="button"
                    onClick={() => onStraighten(0)}
                    title="Кликните для сброса в 0°"
                    className="font-mono font-bold text-amber-400 hover:underline"
                  >
                    {currentTransform.rotation}°
                  </button>
                </div>
                <input
                  type="range"
                  min="-45"
                  max="45"
                  step="1"
                  value={currentTransform.rotation}
                  onChange={(e) => {
                    const v = Number(e.target.value);
                    onStraighten(Math.abs(v) <= 1 ? 0 : v);
                  }}
                  className="accent-amber-500 cursor-pointer"
                />
              </div>
            </div>
          </div>
        )}

        {/* TAB 2: 8 SYNCHRONIZED COLOR SLIDERS */}
        {tab === "adjust" && (
          <div className="flex flex-col gap-3.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                8 фильтров книги
              </span>
              <button
                type="button"
                onClick={() => onApplyPreset("original")}
                className="text-[11px] text-amber-400 hover:text-amber-300"
              >
                Сбросить цвет
              </button>
            </div>

            {[
              { label: "Белый фон (Whiten)", key: "whiten", min: 0, max: 100 },
              { label: "Четкость шрифта", key: "sharpness", min: 0, max: 100 },
              { label: "Яркость", key: "brightness", min: -50, max: 50 },
              { label: "Контрастность", key: "contrast", min: -50, max: 50 },
              { label: "Света / Блики", key: "highlights", min: -50, max: 50 },
              { label: "Тени корешка", key: "shadows", min: -50, max: 50 },
              { label: "Насыщенность", key: "saturation", min: -50, max: 50 },
              { label: "Теплота (ББ)", key: "warmth", min: -50, max: 50 },
            ].map(({ label, key, min, max }) => {
              const fKey = key as keyof StudioTransformState["filters"];
              const val = currentTransform.filters[fKey];
              return (
                <div key={key} className="flex flex-col gap-1">
                  <div className="flex justify-between text-xs text-slate-300">
                    <span>{label}</span>
                    <button
                      type="button"
                      onClick={() => onFilterChange(fKey, 0)}
                      title="Кликните для сброса в 0"
                      className="font-mono text-emerald-400 text-[11px] hover:underline"
                    >
                      {val}
                    </button>
                  </div>
                  <input
                    type="range"
                    min={min}
                    max={max}
                    value={val}
                    onChange={(e) => onFilterChange(fKey, Number(e.target.value))}
                    className="accent-emerald-500 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
                  />
                </div>
              );
            })}
          </div>
        )}

        {/* TAB 3: STYLES & AI REMBG */}
        {tab === "styles" && (
          <div className="flex flex-col gap-4">
            <button
              type="button"
              disabled={isAiProcessing}
              onClick={onRunAiRembg}
              className="w-full rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 py-3 text-xs font-bold text-white shadow-lg hover:from-purple-500 hover:to-indigo-500 active:scale-95 disabled:opacity-50 transition"
            >
              {isAiProcessing ? "⏳ Нейросеть rembg вырезает фон..." : "✨ AI Белый фон (rembg)"}
            </button>

            <div className="space-y-2 border-t border-slate-800 pt-3">
              <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
                Пресеты для книг
              </span>
              <div className="grid grid-cols-1 gap-2">
                {(Object.keys(STUDIO_PRESETS) as Array<keyof typeof STUDIO_PRESETS>).map((k) => (
                  <button
                    key={k}
                    type="button"
                    onClick={() => onApplyPreset(k)}
                    className="flex flex-col items-start rounded-xl border border-slate-800 bg-slate-950/70 px-3 py-2 text-left hover:border-amber-500/60 hover:bg-slate-800 transition"
                  >
                    <span className="text-xs font-semibold text-white">{STUDIO_PRESETS[k].name}</span>
                    <span className="text-[10px] text-slate-400">{STUDIO_PRESETS[k].description}</span>
                  </button>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={onResetAll}
              className="mt-2 w-full rounded-xl border border-rose-800/70 bg-rose-950/50 py-2 text-xs font-semibold text-rose-300 hover:bg-rose-900/70 transition"
            >
              ↺ Сбросить всё к исходнику
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
