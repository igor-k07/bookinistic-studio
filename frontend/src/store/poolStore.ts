/**
 * Photo Pool & Slot Placement Zustand Store.
 *
 * Implements ADR-9 (Unified Asset Registry, Optimistic Locking, slot auto-placement).
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
  { key: "01_cover_front", label: "Обложка (1)", shortcut: "1" },
  { key: "02_title_page", label: "Титул (2)", shortcut: "2" },
  { key: "03_cover_back", label: "Задник (3)", shortcut: "3" },
  { key: "04_spine", label: "Корешок (4)", shortcut: "4" },
  { key: "05_illustration", label: "Разворот (5)", shortcut: "5" },
];

interface PoolState {
  assets: AssetData[];
  selectedAssetId: string | null;
  isLoading: boolean;

  setAssets: (assets: AssetData[]) => void;
  selectAsset: (id: string | null) => void;
  assignSlot: (assetId: string, slot: string, slotOrder?: number) => Promise<void>;
  unassignSlot: (assetId: string) => Promise<void>;
  deleteAsset: (assetId: string) => Promise<void>;
  updateAssetTransform: (
    assetId: string,
    transforms: Record<string, unknown>,
    expectedVersion: number
  ) => Promise<void>;
}

export const usePoolStore = create<PoolState>((set) => ({
  assets: [],
  selectedAssetId: null,
  isLoading: false,

  setAssets: (assets) => set({ assets }),

  selectAsset: (id) => set({ selectedAssetId: id }),

  assignSlot: async (assetId, slot, slotOrder = 0) => {
    try {
      const updated = await apiRequest<AssetData>(`/api/assets/${assetId}/assign`, {
        method: "POST",
        body: JSON.stringify({ slot, slot_order: slotOrder }),
      });

      set((state) => ({
        assets: state.assets.map((a) => (a.id === assetId ? updated : a)),
      }));
    } catch (err) {
      console.error(`Failed to assign slot ${slot} to asset ${assetId}:`, err);
    }
  },

  unassignSlot: async (assetId) => {
    try {
      const updated = await apiRequest<AssetData>(`/api/assets/${assetId}/assign`, {
        method: "POST",
        body: JSON.stringify({ slot: null, slot_order: 0 }),
      });

      set((state) => ({
        assets: state.assets.map((a) => (a.id === assetId ? updated : a)),
      }));
    } catch (err) {
      console.error(`Failed to unassign asset ${assetId}:`, err);
    }
  },

  deleteAsset: async (assetId) => {
    try {
      await apiRequest(`/api/assets/${assetId}`, { method: "DELETE" });
      set((state) => ({
        assets: state.assets.filter((a) => a.id !== assetId),
        selectedAssetId: state.selectedAssetId === assetId ? null : state.selectedAssetId,
      }));
    } catch (err) {
      console.error(`Failed to delete asset ${assetId}:`, err);
    }
  },

  updateAssetTransform: async (assetId, transforms, expectedVersion) => {
    try {
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
    } catch (err) {
      console.error(`Failed to update asset ${assetId} transform:`, err);
      throw err;
    }
  },
}));

// Listen for asset updates from backend via SSE
sseClient.on("asset.updated", (payload) => {
  if (payload?.asset_id) {
    const store = usePoolStore.getState();
    const asset = store.assets.find((a) => a.id === payload.asset_id);
    if (asset) {
      store.setAssets(
        store.assets.map((a) =>
          a.id === payload.asset_id
            ? { ...a, status: payload.status, version: payload.version }
            : a
        )
      );
    }
  }
});
