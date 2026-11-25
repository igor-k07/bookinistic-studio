/**
 * System and configuration Zustand store.
 *
 * Implements ADR-3 (StoreContext synchronization) and ADR-10 (token management).
 */

import { create } from "zustand";
import { apiRequest } from "../api/client";
import { sseClient } from "../api/sse";

export interface StoreProfileInfo {
  store_id: string;
  name: string;
  client_id: string;
  is_test: boolean;
}

interface SystemState {
  isInitialized: boolean;
  activeStore: string;
  stores: StoreProfileInfo[];
  brands: string[];
  gostFormats: Record<string, unknown>;
  mobileToken: string;
  tunnelUrl: string | null;
  outboxCounts: Record<string, number>;
  isLoading: boolean;
  error: string | null;

  hydrateFromBootstrap: () => Promise<void>;
  switchActiveStore: (storeId: string) => Promise<void>;
  fetchOzonStatus: () => Promise<void>;
  rotateMobileToken: () => Promise<void>;
}

export const useSystemStore = create<SystemState>((set, get) => ({
  isInitialized: false,
  activeStore: "default",
  stores: [],
  brands: [],
  gostFormats: {},
  mobileToken: "",
  tunnelUrl: null,
  outboxCounts: {},
  isLoading: false,
  error: null,

  hydrateFromBootstrap: async () => {
    set({ isLoading: true, error: null });
    try {
      const data = await apiRequest<{
        stores: StoreProfileInfo[];
        active_store: string;
        brands: string[];
        gost_formats: Record<string, unknown>;
        mobile_token: string;
        tunnel_url: string | null;
      }>("/api/bootstrap");

      set({
        isInitialized: true,
        activeStore: data.active_store,
        stores: data.stores || [],
        brands: data.brands || [],
        gostFormats: data.gost_formats || {},
        mobileToken: data.mobile_token || "",
        tunnelUrl: data.tunnel_url,
        isLoading: false,
      });

      // Fetch initial outbox counts
      get().fetchOzonStatus();

      // Listen for remote store switch events via SSE
      sseClient.on("store.switched", (payload) => {
        if (payload?.active_store && payload.active_store !== get().activeStore) {
          set({ activeStore: payload.active_store });
        }
      });

      sseClient.on("ozon.status_changed", () => {
        get().fetchOzonStatus();
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      set({ error: msg, isLoading: false });
    }
  },

  switchActiveStore: async (storeId: string) => {
    set({ isLoading: true });
    try {
      const res = await apiRequest<{ status: string; active_store: string }>(
        "/api/ozon/switch-profile",
        {
          method: "POST",
          body: JSON.stringify({ store_id: storeId }),
        }
      );
      set({ activeStore: res.active_store, isLoading: false });
      get().fetchOzonStatus();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      set({ error: msg, isLoading: false });
      throw err;
    }
  },

  fetchOzonStatus: async () => {
    try {
      const res = await apiRequest<{
        active_store: string;
        outbox_counts: Record<string, number>;
      }>("/api/ozon/status");
      if (res.outbox_counts) {
        set({ outboxCounts: res.outbox_counts });
      }
    } catch {
      // Background probe failure is non-blocking
    }
  },

  rotateMobileToken: async () => {
    try {
      const res = await apiRequest<{ mobile_token: string }>("/api/system/tokens/rotate", {
        method: "POST",
      });
      if (res.mobile_token) {
        set({ mobileToken: res.mobile_token });
      }
    } catch (err: unknown) {
      console.error("Failed to rotate token:", err);
      throw err;
    }
  },
}));
