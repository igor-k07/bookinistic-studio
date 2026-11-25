import React, { useEffect, useState } from "react";
import { BarcodeLabel } from "./features/barcode-label/BarcodeLabel";
import { BookForm } from "./features/book-form/BookForm";
import { CatalogTable } from "./features/catalog-table/CatalogTable";
import { PhotoPool } from "./features/photo-pool/PhotoPool";
import { PhotoStudioModal } from "./features/photo-studio/PhotoStudioModal";
import { SettingsModal } from "./features/settings-modals/SettingsModal";
import { usePoolStore, type AssetData } from "./store/poolStore";
import { useSystemStore } from "./store/systemStore";
import { useWorkspaceStore } from "./store/workspaceStore";

export default function App(): React.JSX.Element {
  const {
    activeStore,
    stores,
    outboxCounts,
    hydrateFromBootstrap,
    switchActiveStore,
  } = useSystemStore();

  const {
    tabs,
    activeTabId,
    currentBook,
    createTab,
    closeTab,
    setActiveTab,
  } = useWorkspaceStore();

  const { updateAssetTransform } = usePoolStore();

  const [isStoreMenuOpen, setIsStoreMenuOpen] = useState(false);
  const [selectedStudioAsset, setSelectedStudioAsset] = useState<AssetData | null>(null);
  const [isCatalogOpen, setIsCatalogOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  useEffect(() => {
    hydrateFromBootstrap();
  }, [hydrateFromBootstrap]);

  // Initial tab creation if none exist
  useEffect(() => {
    if (tabs.length === 0) {
      createTab();
    }
  }, [tabs.length, createTab]);

  return (
    <div className="flex h-screen w-screen flex-col bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Top Main Navigation Bar */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-900/90 px-6 backdrop-blur-md">
        <div className="flex items-center gap-4">
          <span className="text-lg font-black tracking-tight text-white">
            Bookinistic Studio <span className="text-emerald-400">2.0</span>
          </span>

          {/* Store Switcher Dropdown */}
          <div className="relative">
            <button
              onClick={() => setIsStoreMenuOpen((prev) => !prev)}
              className="flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1 text-xs font-semibold text-slate-200 hover:border-slate-600 active:scale-95"
            >
              <span>🏬 {stores.find((s) => s.store_id === activeStore)?.name || activeStore}</span>
              <span className="text-slate-400">▼</span>
            </button>

            {isStoreMenuOpen && (
              <div className="absolute top-full left-0 z-50 mt-1.5 w-56 rounded-xl border border-slate-700 bg-slate-800/95 p-1 shadow-2xl backdrop-blur-md">
                {stores.map((s) => (
                  <button
                    key={s.store_id}
                    onClick={() => {
                      switchActiveStore(s.store_id);
                      setIsStoreMenuOpen(false);
                    }}
                    className={`w-full rounded-lg px-3 py-2 text-left text-xs font-medium transition-colors ${
                      s.store_id === activeStore
                        ? "bg-emerald-600 text-white"
                        : "text-slate-300 hover:bg-slate-700"
                    }`}
                  >
                    <div className="font-semibold">{s.name}</div>
                    <div className="text-[10px] text-slate-400">ID: {s.store_id}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Center/Right Navigation Buttons & Live Outbox Status Stats */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsCatalogOpen(true)}
              className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700 hover:text-white active:scale-95 transition-all"
            >
              📚 Каталог
            </button>
            <button
              onClick={() => setIsSettingsOpen(true)}
              className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700 hover:text-white active:scale-95 transition-all"
            >
              ⚙️ Настройки
            </button>
          </div>

          <div className="h-4 w-[1px] bg-slate-800" />

          <div className="flex items-center gap-2 text-xs">
            <span className="text-slate-400">Ozon:</span>
            <span className="rounded bg-amber-950/80 border border-amber-800/80 px-2 py-0.5 text-amber-300 font-semibold">
              В очереди: {outboxCounts["QUEUED"] || 0}
            </span>
            <span className="rounded bg-blue-950/80 border border-blue-800/80 px-2 py-0.5 text-blue-300 font-semibold">
              Модерация: {outboxCounts["PROCESSING"] || outboxCounts["MODERATION"] || 0}
            </span>
            <span className="rounded bg-emerald-950/80 border border-emerald-800/80 px-2 py-0.5 text-emerald-300 font-semibold">
              Опубликовано: {outboxCounts["PUBLISHED"] || 0}
            </span>
          </div>
        </div>
      </header>

      {/* Workspace Tabs Strip */}
      <div className="flex shrink-0 items-center gap-1 overflow-x-auto border-b border-slate-800 bg-slate-900/40 px-4 pt-2 scrollbar-none">
        {tabs.map((tab) => {
          const isActive = tab.id === activeTabId;
          return (
            <div
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`group flex items-center gap-2 rounded-t-xl border-t border-x px-4 py-2 text-xs font-medium transition-all cursor-pointer ${
                isActive
                  ? "border-slate-800 bg-slate-900 text-emerald-400 border-b-2 border-b-emerald-500 shadow-sm"
                  : "border-transparent bg-transparent text-slate-400 hover:bg-slate-850 hover:text-slate-200"
              }`}
            >
              <span className="max-w-[140px] truncate">{tab.title || tab.book_article}</span>
              {tabs.length > 1 && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    closeTab(tab.id);
                  }}
                  className="rounded p-0.5 text-slate-500 opacity-0 transition-opacity group-hover:opacity-100 hover:bg-slate-800 hover:text-red-400"
                >
                  ✕
                </button>
              )}
            </div>
          );
        })}
        <button
          onClick={() => createTab()}
          className="ml-2 mb-1 flex items-center gap-1 rounded-lg border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:border-slate-700 hover:text-white"
        >
          + Новая книга
        </button>
      </div>

      {/* Main Workspace Layout: Two-Column Split */}
      <div className="flex flex-1 overflow-hidden p-4 gap-4">
        {/* Left Column: Comprehensive Book Form */}
        <div className="flex-1 overflow-y-auto pr-1 scrollbar-thin">
          <BookForm />
        </div>

        {/* Right Column: Photo Pool & Barcode Label */}
        <div className="flex w-96 shrink-0 flex-col gap-4 overflow-y-auto pl-1 scrollbar-thin">
          <PhotoPool
            onOpenStudio={(asset) => setSelectedStudioAsset(asset)}
            isStudioOpen={Boolean(selectedStudioAsset)}
          />
          <BarcodeLabel
            article={currentBook.article}
            barcode={currentBook.barcode}
            title={currentBook.title}
            author={currentBook.author}
            price={currentBook.price}
            storageLocation={currentBook.storage_location}
          />
        </div>
      </div>

      {/* Modals */}
      {selectedStudioAsset && (
        <PhotoStudioModal
          asset={selectedStudioAsset}
          isOpen={Boolean(selectedStudioAsset)}
          onClose={() => setSelectedStudioAsset(null)}
          onApplyTransform={async (assetId, transform) => {
            await updateAssetTransform(
              assetId,
              {
                crop: transform.crop,
                rotation: transform.rotation,
                use_ai_white: transform.useAiWhite,
                filters: transform.filters,
              },
              selectedStudioAsset.version || 1
            );
          }}
        />
      )}

      <CatalogTable
        isOpen={isCatalogOpen}
        onClose={() => setIsCatalogOpen(false)}
      />

      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
      />
    </div>
  );
}
