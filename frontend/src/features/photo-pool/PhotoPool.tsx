import React, { useEffect } from "react";
import { PHOTO_SLOTS, usePoolStore, type AssetData } from "../../store/poolStore";
import { ShortcutManager } from "./ShortcutManager";

interface Props {
  onOpenStudio?: (asset: AssetData) => void;
  isStudioOpen?: boolean;
}

export function PhotoPool({ onOpenStudio, isStudioOpen = false }: Props): React.JSX.Element {
  const { assets, selectedAssetId, selectAsset, assignSlot, unassignSlot, deleteAsset } =
    usePoolStore();

  // Filter assigned vs unassigned photos
  const unassigned = assets.filter((a) => !a.slot);

  // Shortcut manager setup
  useEffect(() => {
    const mgr = new ShortcutManager({
      onSlotAssign: (slotNum) => {
        if (!selectedAssetId) return;
        const targetSlot = PHOTO_SLOTS[slotNum - 1];
        if (targetSlot) {
          assignSlot(selectedAssetId, targetSlot.key);
        }
      },
      onDelete: () => {
        if (selectedAssetId) {
          deleteAsset(selectedAssetId);
        }
      },
    });

    mgr.setContext(isStudioOpen ? "STUDIO" : "POOL");
    const cleanup = mgr.attach();

    return () => cleanup();
  }, [selectedAssetId, isStudioOpen, assignSlot, deleteAsset]);

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-slate-800 bg-slate-900/60 p-4 backdrop-blur-md">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold tracking-wide text-slate-200 uppercase">
          Пул фотографий книги
        </h3>
        <span className="text-xs text-slate-400">
          Горячие клавиши: <kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-emerald-400">1-5</kbd> назначить слот,{" "}
          <kbd className="rounded bg-slate-800 px-1.5 py-0.5 text-rose-400">Del</kbd> удалить
        </span>
      </div>

      {/* 5 Standard Slots */}
      <div className="grid grid-cols-5 gap-3">
        {PHOTO_SLOTS.map((slot, sIdx) => {
          const assignedAsset = assets.find((a) => a.slot === slot.key);
          return (
            <div
              key={slot.key}
              onClick={() => {
                if (selectedAssetId && !assignedAsset) {
                  assignSlot(selectedAssetId, slot.key);
                } else if (assignedAsset) {
                  selectAsset(assignedAsset.id);
                }
              }}
              onDoubleClick={() => {
                if (assignedAsset && onOpenStudio) {
                  onOpenStudio(assignedAsset);
                }
              }}
              className={`group relative flex aspect-[3/4] flex-col items-center justify-center rounded-xl border-2 transition-all cursor-pointer ${
                assignedAsset
                  ? assignedAsset.id === selectedAssetId
                    ? "border-emerald-500 bg-slate-800 shadow-lg ring-2 ring-emerald-500/30"
                    : "border-slate-700 bg-slate-800 hover:border-slate-600"
                  : "border-dashed border-slate-800 bg-slate-900/40 hover:border-emerald-500/60"
              }`}
            >
              {assignedAsset ? (
                <>
                  <img
                    src={`/api/assets/${assignedAsset.id}/preview`}
                    alt={slot.label}
                    className="h-full w-full rounded-lg object-cover"
                  />
                  <div className="absolute inset-x-0 bottom-0 rounded-b-lg bg-gradient-to-t from-slate-950 via-slate-950/70 to-transparent p-2 text-center">
                    <span className="block truncate text-[11px] font-semibold text-emerald-300">
                      {slot.label}
                    </span>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      unassignSlot(assignedAsset.id);
                    }}
                    className="absolute top-1.5 right-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-slate-900/80 text-[10px] text-slate-300 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-rose-600 hover:text-white"
                    title="Вернуть в нераспределенные"
                  >
                    ✕
                  </button>
                </>
              ) : (
                <div className="flex flex-col items-center gap-1 text-center p-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-800 text-xs font-bold text-slate-400">
                    {sIdx + 1}
                  </span>
                  <span className="text-[11px] font-medium text-slate-400 leading-tight">
                    {slot.label}
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Unassigned Strip */}
      {unassigned.length > 0 && (
        <div className="mt-2 border-t border-slate-800/80 pt-3">
          <span className="text-xs font-medium text-slate-400">
            Нераспределенные фото ({unassigned.length}):
          </span>
          <div className="mt-2 flex gap-2 overflow-x-auto pb-2 scrollbar-thin">
            {unassigned.map((a) => {
              const isSelected = a.id === selectedAssetId;
              return (
                <div
                  key={a.id}
                  onClick={() => selectAsset(a.id)}
                  onDoubleClick={() => onOpenStudio?.(a)}
                  className={`group relative h-20 w-16 shrink-0 rounded-lg overflow-hidden border-2 cursor-pointer transition-all ${
                    isSelected
                      ? "border-emerald-500 ring-2 ring-emerald-500/40 shadow-md"
                      : "border-slate-800 hover:border-slate-600"
                  }`}
                >
                  <img
                    src={`/api/assets/${a.id}/preview`}
                    alt="Unassigned capture"
                    className="h-full w-full object-cover"
                  />
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteAsset(a.id);
                    }}
                    className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center rounded-full bg-slate-950/80 text-[9px] text-slate-300 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-rose-600"
                  >
                    ✕
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
