/**
 * System and configuration Zustand store.
 *
 * Implements ADR-3 (StoreContext synchronization), ADR-10 (token management),
 * SSE lifecycle startup, and bootstrap tab hydration.
 */

import { create } from "zustand";
import { apiRequest } from "../api/client";
import { sseClient } from "../api/sse";
import { useWorkspaceStore, type WorkspaceTab } from "./workspaceStore";

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
  localUrl: string | null;
  outboxCounts: Record<string, number>;
  isLoading: boolean;
  error: string | null;

  hydrateFromBootstrap: () => Promise<void>;
  switchActiveStore: (storeId: string) => Promise<void>;
  fetchOzonStatus: () => Promise<void>;
  rotateMobileToken: () => Promise<void>;
  restartTunnel: () => Promise<void>;
}

export const useSystemStore = create<SystemState>((set, get) => ({
  isInitialized: false,
  activeStore: "default",
  stores: [],
  brands: [],
  gostFormats: {},
  mobileToken: "",
  tunnelUrl: null,
  localUrl: null,
  outboxCounts: {},
  isLoading: false,
  error: null,

  hydrateFromBootstrap: async () => {
    set({ isLoading: true, error: null });
    try {
      // Establish real-time SSE stream
      sseClient.connect();

      const data = await apiRequest<{
        stores: StoreProfileInfo[];
        active_store: string;
        brands: string[];
        gost_formats: Record<string, unknown>;
        tabs: WorkspaceTab[];
        mobile_token: string;
        tunnel_url: string | null;
        local_url: string | null;
      }>("/api/bootstrap");

      set({
        isInitialized: true,
        activeStore: data.active_store,
        stores: data.stores || [],
        brands: data.brands || [],
        gostFormats: data.gost_formats || {},
        mobileToken: data.mobile_token || "",
        tunnelUrl: data.tunnel_url || null,
        localUrl: data.local_url || null,
        isLoading: false,
      });

      // Hydrate workspace tabs without duplicate-tab race
      const ws = useWorkspaceStore.getState();
      if (data.tabs && data.tabs.length > 0) {
        ws.setTabs(data.tabs);
      } else if (ws.tabs.length === 0) {
        await ws.createTab();
      }

      get().fetchOzonStatus();

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
      set({ error: msg, isLoading: false, isInitialized: true });
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
    const res = await apiRequest<{ mobile_token: string }>("/api/system/tokens/rotate", {
      method: "POST",
    });
    if (res.mobile_token) {
      set({ mobileToken: res.mobile_token });
    }
  },

  restartTunnel: async () => {
    const res = await apiRequest<{ tunnel_url: string | null; local_url: string | null }>(
      "/api/system/tunnel/restart",
      { method: "POST" }
    );
    set({
      tunnelUrl: res.tunnel_url || null,
      localUrl: res.local_url || get().localUrl,
    });
  },
}));
