import React from "react";
import type { StudioTransformState } from "./HistoryStack";

interface Props {
  currentTransform: StudioTransformState;
  onRotate: (deg: number) => void;
  onStraighten: (deg: number) => void;
  onFilterChange: (key: keyof StudioTransformState["filters"], val: number) => void;
}

export function StudioAdjustments({
  currentTransform,
  onRotate,
  onStraighten,
  onFilterChange,
}: Props): React.JSX.Element {
  return (
    <div className="w-80 shrink-0 border-l border-slate-800 bg-slate-900/90 p-5 overflow-y-auto flex flex-col gap-5">
      {/* Rotation & Straighten */}
      <div className="flex flex-col gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
          Поворот и выравнивание
        </span>
        <div className="flex items-center gap-2">
          <button
            onClick={() => onRotate(-90)}
            className="flex-1 rounded-lg bg-slate-800 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700"
          >
            ↺ -90°
          </button>
          <button
            onClick={() => onRotate(90)}
            className="flex-1 rounded-lg bg-slate-800 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700"
          >
            ↻ +90°
          </button>
          <button
            onClick={() => onStraighten(0)}
            className="rounded-lg bg-slate-800 px-2.5 py-1.5 text-xs text-slate-400 hover:text-white"
          >
            Сброс
          </button>
        </div>

        {/* Straighten ruler slider */}
        <div className="mt-1 flex flex-col gap-1">
          <div className="flex justify-between text-[11px] text-slate-400">
            <span>Наклон горизонта</span>
            <span className="font-mono text-emerald-400">{currentTransform.rotation}°</span>
          </div>
          <input
            type="range"
            min="-45"
            max="45"
            step="1"
            value={currentTransform.rotation}
            onChange={(e) => onStraighten(Number(e.target.value))}
            className="accent-emerald-500 cursor-pointer"
          />
        </div>
      </div>

      {/* 8 Post-Processing Sliders */}
      <div className="flex flex-col gap-3.5 border-t border-slate-800 pt-4">
        <span className="text-xs font-semibold uppercase tracking-wider text-slate-300">
          Коррекция книги (8 фильтров)
        </span>

        {[
          { label: "Отбеливание фона", key: "whiten", min: 0, max: 100 },
          { label: "Четкость текста", key: "sharpness", min: 0, max: 100 },
          { label: "Яркость", key: "brightness", min: -100, max: 100 },
          { label: "Контрастность", key: "contrast", min: -100, max: 100 },
          { label: "Света", key: "highlights", min: -100, max: 100 },
          { label: "Тени", key: "shadows", min: -100, max: 100 },
          { label: "Насыщенность", key: "saturation", min: -100, max: 100 },
          { label: "Теплота бумаги", key: "warmth", min: -100, max: 100 },
        ].map(({ label, key, min, max }) => {
          const val = currentTransform.filters[key as keyof StudioTransformState["filters"]];
          return (
            <div key={key} className="flex flex-col gap-1">
              <div className="flex justify-between text-xs text-slate-300">
                <span>{label}</span>
                <span className="font-mono text-emerald-400 text-[11px]">{val}</span>
              </div>
              <input
                type="range"
                min={min}
                max={max}
                value={val}
                onChange={(e) =>
                  onFilterChange(
                    key as keyof StudioTransformState["filters"],
                    Number(e.target.value)
                  )
                }
                className="accent-emerald-500 cursor-pointer h-1.5 bg-slate-800 rounded-lg"
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
