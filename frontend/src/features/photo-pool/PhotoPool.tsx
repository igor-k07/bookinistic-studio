/**
 * PhotoPool — Full-width horizontal Photo Pool, Batch Pipeline & 5 Semantic Slots (v1 parity).
 */

import React, { useEffect, useRef, useState } from "react";
import { PHOTO_SLOTS, usePoolStore, type AssetData } from "../../store/poolStore";
import { useWorkspaceStore } from "../../store/workspaceStore";
import { ShortcutManager } from "./ShortcutManager";

interface Props {
  onOpenStudio?: (asset: AssetData) => void;
  isStudioOpen?: boolean;
}

export function PhotoPool({ onOpenStudio, isStudioOpen = false }: Props): React.JSX.Element {
  const {
    assets,
    selectedAssetId,
    isUploading,
    selectAsset,
    fetchPool,
    uploadFiles,
    assignSlot,
    unassignSlot,
    deleteAsset,
    runAiRembg,
    batchWhitenAll,
    distributeUnassigned,
    clearPool,
  } = usePoolStore();

  const { currentBook } = useWorkspaceStore();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [batchScheme, setBatchScheme] = useState("3");
  const [isAiWorking, setIsAiWorking] = useState(false);

  useEffect(() => {
    fetchPool(currentBook.article || undefined);
  }, [currentBook.article, fetchPool]);

  const unassigned = assets.filter((a) => !a.slot);
  const selectedAsset = assets.find((a) => a.id === selectedAssetId) || null;

  useEffect(() => {
    const mgr = new ShortcutManager({
      onSlotAssign: (slotNum) => {
        if (!selectedAssetId) return;
        const targetSlot = PHOTO_SLOTS[slotNum - 1];
        if (targetSlot) {
          assignSlot(selectedAssetId, targetSlot.key, currentBook.article);
        }
      },
      onDelete: () => {
        if (selectedAssetId) {
          deleteAsset(selectedAssetId);
        }
      },
    });
    mgr.setContext(isStudioOpen ? "STUDIO" : "POOL");
    return mgr.attach();
  }, [selectedAssetId, isStudioOpen, currentBook.article, assignSlot, deleteAsset]);

  const handleQuickAiWhite = async () => {
    if (!selectedAsset || isAiWorking) return;
    setIsAiWorking(true);
    try {
      await runAiRembg(selectedAsset.id);
    } finally {
      setIsAiWorking(false);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      {/* SECTION 1: FULL-WIDTH PHOTO POOL */}
      <section className="rounded-3xl border border-slate-800 bg-slate-900/90 p-5 shadow-2xl space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="text-lg">📸</span>
            <h2 className="text-sm font-bold text-white uppercase tracking-wide">Пул фотографий</h2>
            <span className="rounded-full bg-slate-800 px-3 py-0.5 text-xs font-mono text-amber-300 border border-slate-700">
              {unassigned.length} в ленте · {assets.length} всего
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                if (e.target.files) {
                  uploadFiles(e.target.files, currentBook.article);
                  e.target.value = "";
                }
              }}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading}
              className="rounded-xl border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 hover:text-white active:scale-95 transition disabled:opacity-50"
            >
              {isUploading ? "⏳ Загрузка..." : "📂 Выбрать файлы с диска"}
            </button>
            <button
              type="button"
              onClick={() => batchWhitenAll()}
              className="rounded-xl border border-emerald-800 bg-emerald-950/80 px-3.5 py-2 text-xs font-semibold text-emerald-300 hover:bg-emerald-900 active:scale-95 transition"
            >
              ✨ Отбелить пул
            </button>
            {unassigned.length > 0 && (
              <button
                type="button"
                onClick={() => {
                  if (confirm(`Очистить ${unassigned.length} нераспределенных фото из пула?`)) {
                    clearPool();
                  }
                }}
                className="rounded-xl border border-rose-800/70 bg-rose-950/60 px-3 py-2 text-xs font-semibold text-rose-300 hover:bg-rose-900 active:scale-95 transition"
              >
                🧹 Очистить пул
              </button>
            )}
          </div>
        </div>

        {/* Batch Pipeline Toolbar */}
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-500/30 bg-gradient-to-r from-slate-900 via-amber-950/20 to-slate-900 p-3 text-xs">
          <div className="flex flex-wrap items-center gap-3">
            <span className="font-bold text-amber-300">⚡ Пакетный конвейер:</span>
            <select
              value={batchScheme}
              onChange={(e) => setBatchScheme(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-950 px-2.5 py-1 text-xs text-slate-200"
            >
              <option value="3">по 3 фото (Обложка + Задник + Титул)</option>
              <option value="4">по 4 фото (+ Иллюстрация)</option>
              <option value="5">по 5 фото (+ Дефекты)</option>
              <option value="2">по 2 фото (Обложка + Титул)</option>
            </select>
          </div>
          <button
            type="button"
            disabled={unassigned.length === 0}
            onClick={() => distributeUnassigned(batchScheme, currentBook.article)}
            className="rounded-xl bg-amber-600 px-3.5 py-1.5 text-xs font-bold text-white hover:bg-amber-500 active:scale-95 disabled:opacity-40 transition"
          >
            ⚡ Разложить по слотам
          </button>
        </div>

        {/* Selected Photo Action Bar + 1..5 Role Buttons */}
        <div className="flex flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-950/90 p-3 text-xs">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="font-mono text-slate-300 truncate max-w-xs">
              {selectedAsset
                ? `Выбрано: ${selectedAsset.original_path.split("/").pop() || selectedAsset.id}`
                : "Выберите фото из ленты или слотов (клавиши 1..5)"}
            </span>
            {selectedAsset && (
              <div className="flex flex-wrap items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => onOpenStudio?.(selectedAsset)}
                  className="rounded-lg bg-amber-600/90 px-2.5 py-1 text-xs font-semibold text-white hover:bg-amber-500"
                >
                  ✂️ Фото-студия Pro
                </button>
                <button
                  type="button"
                  disabled={isAiWorking}
                  onClick={handleQuickAiWhite}
                  className="rounded-lg bg-purple-600/90 px-2.5 py-1 text-xs font-semibold text-white hover:bg-purple-500 disabled:opacity-50"
                >
                  {isAiWorking ? "⏳ rembg..." : "✨ AI Белый фон"}
                </button>
                <button
                  type="button"
                  onClick={() => deleteAsset(selectedAsset.id)}
                  className="rounded-lg bg-rose-950/80 border border-rose-800 px-2.5 py-1 text-xs font-semibold text-rose-300 hover:bg-rose-900"
                >
                  🗑️ Удалить
                </button>
              </div>
            )}
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-2">
            {PHOTO_SLOTS.map((slot) => (
              <button
                key={slot.key}
                type="button"
                disabled={!selectedAssetId}
                onClick={() =>
                  selectedAssetId && assignSlot(selectedAssetId, slot.key, currentBook.article)
                }
                className="flex items-center justify-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800/90 px-3 py-2 text-xs font-semibold text-slate-100 hover:border-amber-500/60 hover:bg-slate-800 disabled:opacity-40 transition"
              >
                <span className="rounded bg-black/50 px-1.5 py-0.5 font-mono text-[10px] text-amber-300">
                  {slot.shortcut}
                </span>
                <span>{slot.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Large Horizontal Photo Strip */}
        <div className="flex gap-4 overflow-x-auto pb-2 pt-1 min-h-[240px] items-stretch">
          {unassigned.length === 0 ? (
            <div className="flex w-full flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-slate-800 bg-slate-950/40 py-12 text-center text-xs text-slate-500">
              <span className="text-3xl">📸</span>
              <span>
                Пул пуст. Снимите пачку книг на телефон через QR-код или нажмите «Выбрать файлы с диска»
              </span>
            </div>
          ) : (
            unassigned.map((asset) => {
              const isSelected = asset.id === selectedAssetId;
              return (
                <div
                  key={asset.id}
                  onClick={() => selectAsset(asset.id)}
                  onDoubleClick={() => onOpenStudio?.(asset)}
                  className={`group relative flex w-44 shrink-0 flex-col overflow-hidden rounded-2xl border-2 bg-slate-950 cursor-pointer transition-all ${
                    isSelected
                      ? "border-amber-500 ring-2 ring-amber-500/40 shadow-xl"
                      : "border-slate-800 hover:border-slate-600"
                  }`}
                >
                  <div className="relative h-48 w-full overflow-hidden bg-slate-900">
                    <img
                      src={`/api/assets/${asset.id}/preview?v=${asset.version}`}
                      alt="Pool item"
                      className="h-full w-full object-contain"
                    />
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onOpenStudio?.(asset);
                      }}
                      className="absolute left-2 top-2 rounded-lg bg-black/75 px-2 py-1 text-[11px] text-amber-300 opacity-0 group-hover:opacity-100 hover:bg-amber-600 hover:text-white transition"
                    >
                      ✂️ Студия
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        deleteAsset(asset.id);
                      }}
                      className="absolute right-2 top-2 rounded-lg bg-black/75 px-2 py-1 text-xs text-rose-400 opacity-0 group-hover:opacity-100 hover:bg-rose-600 hover:text-white transition"
                    >
                      ✕
                    </button>
                  </div>
                  <div className="flex items-center justify-between px-2.5 py-1.5 text-[10px] font-mono text-slate-400 bg-slate-950 border-t border-slate-800">
                    <span className="truncate">{asset.original_path.split("/").pop() || asset.id}</span>
                    {asset.ai_white_path && <span className="text-purple-400 font-bold">AI</span>}
                  </div>
                </div>
              );
            })
          )}
        </div>
      </section>

      {/* SECTION 2: 5 WIDE SEMANTIC BOOK SLOTS */}
      <section className="rounded-3xl border border-slate-800 bg-slate-900/90 p-5 shadow-2xl space-y-3">
        <div className="flex items-center justify-between border-b border-slate-800 pb-2.5">
          <h3 className="text-sm font-bold text-white uppercase tracking-wide">
            📑 Слоты фотографий активной книги ({currentBook.article || "Черновик"})
          </h3>
          <span className="text-xs text-slate-400">
            Двойной клик по фото открывает Фото-студию Pro
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {PHOTO_SLOTS.map((slot) => {
            const slotAssets = assets.filter((a) => a.slot === slot.key);
            return (
              <div
                key={slot.key}
                onClick={() => {
                  if (selectedAssetId) {
                    assignSlot(selectedAssetId, slot.key, currentBook.article);
                  }
                }}
                className={`flex min-h-[240px] flex-col rounded-2xl border-2 p-3 transition-all ${
                  slotAssets.length > 0
                    ? "border-slate-700 bg-slate-950/80"
                    : "border-dashed border-slate-800 bg-slate-950/30 hover:border-amber-500/50 cursor-pointer"
                }`}
              >
                <div className="mb-2 flex items-center justify-between text-xs font-bold text-slate-200">
                  <span>{slot.label}</span>
                  <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-mono text-amber-300">
                    {slotAssets.length}
                  </span>
                </div>

                {slotAssets.length === 0 ? (
                  <div className="flex flex-1 items-center justify-center text-center text-[11px] text-slate-500 px-2">
                    Кликните сюда или нажмите{" "}
                    <kbd className="mx-1 rounded bg-slate-800 px-1 text-slate-300">{slot.shortcut}</kbd>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 gap-2 flex-1">
                    {slotAssets.map((a) => (
                      <div
                        key={a.id}
                        onClick={(e) => {
                          e.stopPropagation();
                          selectAsset(a.id);
                        }}
                        onDoubleClick={(e) => {
                          e.stopPropagation();
                          onOpenStudio?.(a);
                        }}
                        className={`group relative flex h-44 items-center justify-center overflow-hidden rounded-xl border bg-slate-900 cursor-pointer ${
                          a.id === selectedAssetId
                            ? "border-amber-500 ring-2 ring-amber-500/30"
                            : "border-slate-800 hover:border-slate-600"
                        }`}
                      >
                        <img
                          src={`/api/assets/${a.id}/preview?v=${a.version}`}
                          alt={slot.label}
                          className="h-full w-full object-contain"
                        />
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            unassignSlot(a.id);
                          }}
                          title="Вернуть в пул"
                          className="absolute right-1.5 top-1.5 rounded-lg bg-black/75 px-2 py-0.5 text-xs text-rose-400 opacity-0 group-hover:opacity-100 hover:bg-rose-600 hover:text-white transition"
                        >
                          ↩
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>
    </div>
  );
}
