/**
 * Photo Pool & 5-Slot Semantic Pipeline Zustand Store (v1 logic on 2.0 Asset Registry).
 */

import { create } from "zustand";
import { apiRequest } from "../api/client";
import { sseClient } from "../api/sse";

export interface AssetData {
  id: string;
  book_article?: string | null;
  slot?: string | null;
  slot_order: number;
  status: string;
  status_message: string;
  original_path: string;
  preview_path: string;
  ai_white_path?: string | null;
  transformations: Record<string, unknown>;
  render_hash: string;
  s3_staging_url?: string | null;
  s3_final_url?: string | null;
  version: number;
  file_size_bytes: number;
}

export const PHOTO_SLOTS = [
  { key: "cover_front", label: "🌟 1. Обложка (перед)", shortcut: "1", multi: false },
  { key: "cover_back", label: "🔄 2. Обложка (зад)", shortcut: "2", multi: true },
  { key: "info_pages", label: "📄 3. Титул и мантра (ИИ)", shortcut: "3", multi: true },
  { key: "illustrations", label: "🎨 4. Иллюстрации", shortcut: "4", multi: true },
  { key: "mantra_defects", label: "⚠️ 5. Только дефекты", shortcut: "5", multi: true },
] as const;

interface PoolState {
  assets: AssetData[];
  selectedAssetId: string | null;
  isLoading: boolean;
  isUploading: boolean;

  setAssets: (assets: AssetData[]) => void;
  selectAsset: (id: string | null) => void;
  fetchPool: (bookArticle?: string) => Promise<void>;
  uploadFiles: (files: FileList | File[], bookArticle?: string) => Promise<void>;
  assignSlot: (assetId: string, slot: string, bookArticle?: string, slotOrder?: number) => Promise<void>;
  unassignSlot: (assetId: string) => Promise<void>;
  deleteAsset: (assetId: string) => Promise<void>;
  updateAssetTransform: (
    assetId: string,
    transforms: Record<string, unknown>,
    expectedVersion: number
  ) => Promise<AssetData>;
  runAiRembg: (assetId: string) => Promise<AssetData>;
  batchWhitenAll: () => Promise<void>;
  distributeUnassigned: (scheme: string, bookArticle: string) => Promise<void>;
}

export const usePoolStore = create<PoolState>((set, get) => ({
  assets: [],
  selectedAssetId: null,
  isLoading: false,
  isUploading: false,

  setAssets: (assets) => set({ assets }),
  selectAsset: (id) => set({ selectedAssetId: id }),

  fetchPool: async (bookArticle?: string) => {
    set({ isLoading: true });
    try {
      const url = bookArticle
        ? `/api/assets/pool?book_article=${encodeURIComponent(bookArticle)}`
        : "/api/assets/pool";
      const list = await apiRequest<AssetData[]>(url);
      set({ assets: list || [], isLoading: false });
    } catch (err) {
      console.error("Failed to fetch photo pool:", err);
      set({ isLoading: false });
    }
  },

  uploadFiles: async (files, bookArticle) => {
    const fileArr = Array.from(files);
    if (fileArr.length === 0) return;

    set({ isUploading: true });
    try {
      const uploaded: AssetData[] = [];
      for (const file of fileArr) {
        const formData = new FormData();
        formData.append("file", file);
        if (bookArticle) formData.append("book_article", bookArticle);

        const resp = await fetch("/api/assets/upload", { method: "POST", body: formData });
        if (resp.ok) {
          uploaded.push((await resp.json()) as AssetData);
        }
      }
      if (uploaded.length > 0) {
        set((state) => ({
          assets: [...uploaded, ...state.assets],
          selectedAssetId: state.selectedAssetId || uploaded[0].id,
        }));
      }
    } finally {
      set({ isUploading: false });
    }
  },

  assignSlot: async (assetId, slot, bookArticle, slotOrder = 0) => {
    // v1 rule: cover_front is single — return previous cover_front back to pool
    if (slot === "cover_front") {
      const prev = get().assets.find((a) => a.slot === "cover_front" && a.id !== assetId);
      if (prev) {
        await get().unassignSlot(prev.id);
      }
    }

    const updated = await apiRequest<AssetData>(`/api/assets/${assetId}/assign`, {
      method: "POST",
      body: JSON.stringify({ slot, slot_order: slotOrder, book_article: bookArticle || null }),
    });
    set((state) => ({
      assets: state.assets.map((a) => (a.id === assetId ? updated : a)),
    }));
  },

  unassignSlot: async (assetId) => {
    const updated = await apiRequest<AssetData>(`/api/assets/${assetId}/assign`, {
      method: "POST",
      body: JSON.stringify({ slot: null, slot_order: 0, book_article: null }),
    });
    set((state) => ({
      assets: state.assets.map((a) => (a.id === assetId ? updated : a)),
    }));
  },

  deleteAsset: async (assetId) => {
    await apiRequest(`/api/assets/${assetId}`, { method: "DELETE" });
    set((state) => ({
      assets: state.assets.filter((a) => a.id !== assetId),
      selectedAssetId: state.selectedAssetId === assetId ? null : state.selectedAssetId,
    }));
  },

  updateAssetTransform: async (assetId, transforms, expectedVersion) => {
    const updated = await apiRequest<AssetData>(`/api/assets/${assetId}/transform`, {
      method: "PATCH",
      body: JSON.stringify({
        transformations: transforms,
        expected_version: expectedVersion,
      }),
    });
    set((state) => ({
      assets: state.assets.map((a) => (a.id === assetId ? updated : a)),
    }));
    return updated;
  },

  runAiRembg: async (assetId) => {
    const updated = await apiRequest<AssetData>(`/api/assets/${assetId}/run-ai?force=true`, {
      method: "POST",
    });
    set((state) => ({
      assets: state.assets.map((a) => (a.id === assetId ? updated : a)),
    }));
    return updated;
  },

  batchWhitenAll: async () => {
    const targets = get().assets.filter((a) => !a.ai_white_path);
    for (const a of targets) {
      try {
        await get().updateAssetTransform(
          a.id,
          {
            ...(a.transformations || {}),
            filters: {
              ...((a.transformations?.filters as Record<string, unknown>) || {}),
              whiten: 35,
              contrast: 10,
              sharpness: 15,
            },
          },
          a.version || 1
        );
      } catch (err) {
        console.warn("Batch whiten skipped for", a.id, err);
      }
    }
  },

  distributeUnassigned: async (scheme, bookArticle) => {
    const unassigned = get().assets.filter((a) => !a.slot);
    if (unassigned.length === 0) return;

    const perBook = Number(scheme) || 3;
    const roleOrder =
      perBook === 2
        ? ["cover_front", "info_pages"]
        : perBook === 3
        ? ["cover_front", "cover_back", "info_pages"]
        : perBook === 4
        ? ["cover_front", "cover_back", "info_pages", "illustrations"]
        : ["cover_front", "cover_back", "info_pages", "illustrations", "mantra_defects"];

    for (let i = 0; i < Math.min(unassigned.length, roleOrder.length); i++) {
      await get().assignSlot(unassigned[i].id, roleOrder[i], bookArticle, i);
    }
  },
}));

sseClient.on("asset.updated", (rawPayload) => {
  const payload = rawPayload as {
    asset_id?: string;
    status?: string;
    version?: number;
    slot?: string | null;
  } | null;
  if (payload?.asset_id) {
    const store = usePoolStore.getState();
    const exists = store.assets.some((a) => a.id === payload.asset_id);
    if (exists) {
      store.setAssets(
        store.assets.map((a) =>
          a.id === payload.asset_id
            ? {
                ...a,
                status: payload.status ?? a.status,
                version: payload.version ?? a.version,
                slot: payload.slot !== undefined ? payload.slot : a.slot,
              }
            : a
        )
      );
    }
  }
});

sseClient.on("mobile.committed", () => {
  usePoolStore.getState().fetchPool();
});
