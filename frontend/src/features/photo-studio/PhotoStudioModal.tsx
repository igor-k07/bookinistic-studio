/**
 * PhotoStudioModal — Modular Photo Studio Pro (v1 UX + 2.0 isolated StudioEngine & Diff HistoryStack).
 */

import React, { useEffect, useRef, useState, useCallback } from "react";
import "cropperjs/dist/cropper.css";
import { usePoolStore, type AssetData } from "../../store/poolStore";
import { HistoryStack, type StudioTransformState } from "./HistoryStack";
import { StudioAdjustments } from "./StudioAdjustments";
import { StudioEngine, type CropRatio } from "./StudioEngine";

interface Props {
  asset: AssetData;
  isOpen: boolean;
  onClose: () => void;
  onApplyTransform: (assetId: string, transform: StudioTransformState) => Promise<void>;
}

function extractTransformFromAsset(asset: AssetData): StudioTransformState {
  const t = (asset.transformations || {}) as Record<string, unknown>;
  const f = ((t.filters as Record<string, unknown>) || {}) as Record<string, unknown>;
  return {
    crop: (t.crop as StudioTransformState["crop"]) || null,
    rotation: typeof t.rotation === "number" ? t.rotation : 0,
    useAiWhite: Boolean(t.use_ai_white || asset.ai_white_path),
    filters: {
      brightness: Number(f.brightness) || 0,
      contrast: Number(f.contrast) || 0,
      saturation: Number(f.saturation) || 0,
      sharpness: Number(f.sharpness) || 0,
      highlights: Number(f.highlights) || 0,
      shadows: Number(f.shadows) || 0,
      whiten: Number(f.whiten) || 0,
      warmth: Number(f.warmth) || 0,
    },
  };
}

export function PhotoStudioModal({
  asset,
  isOpen,
  onClose,
  onApplyTransform,
}: Props): React.JSX.Element | null {
  const imgRef = useRef<HTMLImageElement>(null);
  const engineRef = useRef<StudioEngine | null>(null);
  const historyRef = useRef<HistoryStack | null>(null);

  const { runAiRembg } = usePoolStore();
  const [imgVersion, setImgVersion] = useState<number>(asset.version || 1);
  const [currentTransform, setCurrentTransform] = useState<StudioTransformState>(() =>
    extractTransformFromAsset(asset)
  );
  const [cropRatio, setCropRatio] = useState<CropRatio>("3:4");
  const [showOriginal, setShowOriginal] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [isAiProcessing, setIsAiProcessing] = useState(false);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  const syncHistoryState = useCallback(() => {
    if (historyRef.current) {
      setCanUndo(historyRef.current.canUndo());
      setCanRedo(historyRef.current.canRedo());
    }
  }, []);

  useEffect(() => {
    if (!isOpen) return;

    const initial = extractTransformFromAsset(asset);
    setCurrentTransform(initial);
    setImgVersion(asset.version || 1);

    const history = new HistoryStack(initial);
    historyRef.current = history;

    const engine = new StudioEngine(initial, (newState) => {
      setCurrentTransform(newState);
      history.push(newState);
      syncHistoryState();
    });
    engineRef.current = engine;

    if (imgRef.current) {
      engine.init(imgRef.current);
    }

    return () => {
      engine.destroy();
      engineRef.current = null;
      historyRef.current = null;
    };
  }, [isOpen, asset.id, imgVersion, syncHistoryState]);

  const handleApply = useCallback(async () => {
    if (!engineRef.current || isApplying) return;
    setIsApplying(true);
    try {
      const finalTransform = engineRef.current.getTransform();
      await onApplyTransform(asset.id, finalTransform);
      onClose();
    } catch (err) {
      console.error("Failed to save transform:", err);
    } finally {
      setIsApplying(false);
    }
  }, [asset.id, isApplying, onApplyTransform, onClose]);

  const handleUndo = useCallback(() => {
    if (!historyRef.current || !engineRef.current) return;
    const prev = historyRef.current.undo();
    if (prev) {
      engineRef.current.applyState(prev);
      setCurrentTransform(prev);
      syncHistoryState();
    }
  }, [syncHistoryState]);

  const handleRedo = useCallback(() => {
    if (!historyRef.current || !engineRef.current) return;
    const next = historyRef.current.redo();
    if (next) {
      engineRef.current.applyState(next);
      setCurrentTransform(next);
      syncHistoryState();
    }
  }, [syncHistoryState]);

  const handleRunAiRembg = useCallback(async () => {
    if (isAiProcessing) return;
    setIsAiProcessing(true);
    try {
      const updated = await runAiRembg(asset.id);
      engineRef.current?.setAiWhite(true);
      setImgVersion((updated.version || imgVersion) + 1);
    } catch (err) {
      console.error("AI rembg failed:", err);
    } finally {
      setIsAiProcessing(false);
    }
  }, [asset.id, imgVersion, isAiProcessing, runAiRembg]);

  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleApply();
      } else if (e.code === "Space" && !e.repeat) {
        e.preventDefault();
        setShowOriginal(true);
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) handleRedo();
        else handleUndo();
      } else if (e.key.toLowerCase() === "r" && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        engineRef.current?.rotateStep(e.shiftKey ? -90 : 90);
      }
    };

    const handleKeyUp = (e: KeyboardEvent) => {
      if (e.code === "Space") {
        e.preventDefault();
        setShowOriginal(false);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("keyup", handleKeyUp);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
    };
  }, [isOpen, onClose, handleApply, handleUndo, handleRedo]);

  if (!isOpen) return null;

  const previewUrl = `/api/assets/${asset.id}/preview?v=${imgVersion}`;
  const fullOriginalUrl = `/api/assets/${asset.id}/full`;
  const fileName = asset.original_path ? asset.original_path.split("/").pop() : asset.id;

  const f = currentTransform.filters;
  const cssBrightness = 1 + (f.brightness + f.whiten * 0.35 + f.highlights * 0.15) / 100;
  const cssContrast = 1 + (f.contrast + f.whiten * 0.15 + f.sharpness * 0.12) / 100;
  const cssSaturate = Math.max(0, 1 + f.saturation / 100);
  const cssSepia = f.warmth > 0 ? Math.min(0.55, f.warmth / 120) : 0;
  const cssFilter = `brightness(${cssBrightness.toFixed(2)}) contrast(${cssContrast.toFixed(
    2
  )}) saturate(${cssSaturate.toFixed(2)}) sepia(${cssSepia.toFixed(2)})`;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 backdrop-blur-md p-5">
      <div className="flex h-full max-h-[92vh] w-full max-w-7xl flex-col rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl overflow-hidden">
        {/* Top Control Bar */}
        <div className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-950/90 px-6">
          <div className="flex items-center gap-3">
            <span className="font-bold text-slate-100">📸 Фото-студия Pro:</span>
            <span className="text-xs text-slate-400 font-mono">{fileName}</span>
            {currentTransform.useAiWhite && (
              <span className="rounded-full bg-purple-600/30 border border-purple-500/50 px-2 py-0.5 text-[10px] font-bold text-purple-300">
                ✨ AI Белый фон
              </span>
            )}
          </div>

          <div className="flex items-center gap-2.5">
            <button
              type="button"
              onClick={handleUndo}
              disabled={!canUndo}
              className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${
                canUndo ? "bg-slate-800 text-slate-200 hover:bg-slate-700" : "opacity-40 text-slate-500"
              }`}
            >
              ↩ Назад
            </button>
            <button
              type="button"
              onClick={handleRedo}
              disabled={!canRedo}
              className={`rounded-lg px-2.5 py-1 text-xs font-semibold ${
                canRedo ? "bg-slate-800 text-slate-200 hover:bg-slate-700" : "opacity-40 text-slate-500"
              }`}
            >
              ↪ Вперед
            </button>

            <button
              type="button"
              onMouseDown={() => setShowOriginal(true)}
              onMouseUp={() => setShowOriginal(false)}
              onMouseLeave={() => setShowOriginal(false)}
              className="rounded-lg border border-amber-700/60 bg-amber-950/50 px-2.5 py-1 text-xs font-semibold text-amber-300 hover:bg-amber-900/60"
            >
              👁️ Оригинал (Пробел)
            </button>

            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700"
            >
              Отмена (Esc)
            </button>
            <button
              type="button"
              onClick={handleApply}
              disabled={isApplying}
              className="rounded-lg bg-emerald-600 px-4 py-1.5 text-xs font-bold text-white shadow-lg hover:bg-emerald-500 active:scale-95 disabled:opacity-50"
            >
              {isApplying ? "Сохранение..." : "Применить (Enter)"}
            </button>
          </div>
        </div>

        {/* Studio Workspace */}
        <div className="flex flex-1 overflow-hidden">
          <div className="relative flex flex-1 items-center justify-center bg-slate-950 p-4">
            {showOriginal ? (
              <div className="flex flex-col items-center gap-2">
                <span className="rounded-full bg-amber-500/20 px-3 py-0.5 text-xs font-bold text-amber-300 border border-amber-500/40">
                  Исходный снимок камеры (без правок)
                </span>
                <img
                  src={fullOriginalUrl}
                  alt="Original"
                  className="max-h-[70vh] max-w-full rounded-lg object-contain shadow-2xl"
                />
              </div>
            ) : (
              <div
                className="relative h-[72vh] w-full overflow-hidden rounded-lg bg-slate-950"
                style={{ filter: cssFilter }}
              >
                <img
                  ref={imgRef}
                  src={previewUrl}
                  alt="Editable"
                  crossOrigin="anonymous"
                  className="block max-w-full"
                />
              </div>
            )}
          </div>

          <StudioAdjustments
            currentTransform={currentTransform}
            cropRatio={cropRatio}
            isAiProcessing={isAiProcessing}
            onCropRatioChange={(ratio) => {
              setCropRatio(ratio);
              engineRef.current?.setCropRatio(ratio);
            }}
            onRotate={(deg) => engineRef.current?.rotateStep(deg)}
            onStraighten={(deg) => engineRef.current?.setRotation(deg)}
            onFilterChange={(key, val) => engineRef.current?.setFilter(key, val)}
            onApplyPreset={(k) => engineRef.current?.applyPreset(k)}
            onRunAiRembg={handleRunAiRembg}
            onResetAll={() => engineRef.current?.reset()}
          />
        </div>
      </div>
    </div>
  );
}
