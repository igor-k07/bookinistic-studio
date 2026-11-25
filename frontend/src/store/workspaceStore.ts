/**
 * Desktop Workspace & Book Form Zustand Store.
 *
 * Implements ADR-4 (Era boundary SSOT), ADR-7 (Single Save Button), and ADR-9 (Draft Tabs).
 */

import { create } from "zustand";
import { apiRequest } from "../api/client";
import { sseClient } from "../api/sse";

export interface BookData {
  article: string;
  title: string;
  author: string;
  year: number | null;
  price: number;
  old_price: number | null;
  template_mode: "pre2011" | "post2011";
  status: string;
  storage_location: string;
  publisher: string;
  series: string;
  isbn: string;
  format_code: string;
  pages: number;
  cover_type: string;
  condition: string;
  annotation: string;
  brand: string;
  author_cover: string;
  original_title: string;
  barcode: string;
  genre: string;
  paper_type: string;
  age_limit: string;
  translator: string;
  illustrator: string;
  main_photo_url: string;
  add_photo_urls: string[];
  dimensions: {
    width_mm: number;
    length_mm: number;
    height_mm: number;
    weight_g: number;
    book_format_code: string;
  };
  field_sources: Record<string, number>;
  suggestions: Record<string, unknown>;
  ozon_sync_status?: string | null;
}

export interface WorkspaceTab {
  id: string;
  book_article: string;
  tab_order: number;
  is_active: boolean;
  is_edit_mode: boolean;
  title: string;
  created_at?: string | null;
}

interface WorkspaceState {
  tabs: WorkspaceTab[];
  activeTabId: string | null;
  currentBook: BookData;
  validationErrors: Record<string, string>;
  isSaving: boolean;
  saveMessage: string | null;

  setTabs: (tabs: WorkspaceTab[]) => void;
  setActiveTab: (tabId: string) => Promise<void>;
  createTab: (article?: string, title?: string) => Promise<void>;
  closeTab: (tabId: string) => Promise<void>;
  updateBookField: <K extends keyof BookData>(field: K, value: BookData[K]) => void;
  updateDimensions: (dims: Partial<BookData["dimensions"]>) => void;
  validateCurrentBook: () => Promise<boolean>;
  saveCurrentBook: () => Promise<{ success: boolean; errors?: Record<string, string> }>;
  reopenBook: (article: string) => Promise<void>;
}

const DEFAULT_BOOK: BookData = {
  article: "",
  title: "",
  author: "не указан",
  year: null,
  price: 0,
  old_price: null,
  template_mode: "pre2011",
  status: "DRAFT",
  storage_location: "",
  publisher: "",
  series: "",
  isbn: "",
  format_code: "84×108/32",
  pages: 0,
  cover_type: "Твердый переплет",
  condition: "Хорошая",
  annotation: "",
  brand: "",
  author_cover: "",
  original_title: "",
  barcode: "",
  genre: "Проза",
  paper_type: "Типографская",
  age_limit: "",
  translator: "",
  illustrator: "",
  main_photo_url: "",
  add_photo_urls: [],
  dimensions: {
    width_mm: 130,
    length_mm: 200,
    height_mm: 15,
    weight_g: 250,
    book_format_code: "84×108/32",
  },
  field_sources: {},
  suggestions: {},
  ozon_sync_status: null,
};

export const useWorkspaceStore = create<WorkspaceState>((set, get) => ({
  tabs: [],
  activeTabId: null,
  currentBook: { ...DEFAULT_BOOK },
  validationErrors: {},
  isSaving: false,
  saveMessage: null,

  setTabs: (tabs) => {
    set({ tabs });
    const active = tabs.find((t) => t.is_active) || tabs[0];
    if (active) {
      get().setActiveTab(active.id);
    }
  },

  setActiveTab: async (tabId: string) => {
    const tab = get().tabs.find((t) => t.id === tabId);
    if (!tab) return;

    // Update active tab locally and notify backend
    set((state) => ({
      activeTabId: tabId,
      tabs: state.tabs.map((t) => ({ ...t, is_active: t.id === tabId })),
      validationErrors: {},
      saveMessage: null,
    }));

    try {
      await apiRequest(`/api/tabs/${tabId}`, {
        method: "PATCH",
        body: JSON.stringify({ is_active: true }),
      });

      // Load book for this tab
      const book = await apiRequest<BookData>(`/api/books/${tab.book_article}`);
      set({ currentBook: book });
    } catch {
      // If book not found, set default with article
      set({
        currentBook: {
          ...DEFAULT_BOOK,
          article: tab.book_article,
          title: tab.title || tab.book_article,
        },
      });
    }
  },

  createTab: async (article?: string, title?: string) => {
    const targetArticle = article || `DP-B-${Date.now().toString().slice(-5)}`;
    const tabId = `tab_${targetArticle.toLowerCase()}`;
    const newTab: WorkspaceTab = {
      id: tabId,
      book_article: targetArticle,
      tab_order: get().tabs.length,
      is_active: true,
      is_edit_mode: false,
      title: title || targetArticle,
    };

    try {
      const created = await apiRequest<WorkspaceTab>("/api/tabs", {
        method: "POST",
        body: JSON.stringify(newTab),
      });

      set((state) => ({
        tabs: [...state.tabs.map((t) => ({ ...t, is_active: false })), created],
        activeTabId: created.id,
        currentBook: {
          ...DEFAULT_BOOK,
          article: created.book_article,
          title: created.title,
        },
        validationErrors: {},
      }));
    } catch (err) {
      console.error("Failed to create tab:", err);
    }
  },

  closeTab: async (tabId: string) => {
    const remaining = get().tabs.filter((t) => t.id !== tabId);
    try {
      await apiRequest(`/api/tabs/${tabId}`, { method: "DELETE" });
      set({ tabs: remaining });
      if (get().activeTabId === tabId && remaining.length > 0) {
        get().setActiveTab(remaining[0].id);
      }
    } catch (err) {
      console.error("Failed to close tab:", err);
    }
  },

  updateBookField: (field, value) => {
    set((state) => {
      const updated = { ...state.currentBook, [field]: value };

      // ADR-4: Era boundary SSOT auto-switch
      if (field === "year") {
        const yr = value as number | null;
        if (yr !== null && yr !== undefined) {
          updated.template_mode = yr >= 2011 ? "post2011" : "pre2011";
        }
      }

      // Track USER_MANUAL provenance (priority 5)
      updated.field_sources = {
        ...updated.field_sources,
        [String(field)]: 5,
      };

      return {
        currentBook: updated,
        validationErrors: { ...state.validationErrors, [String(field)]: "" },
      };
    });
  },

  updateDimensions: (dims) => {
    set((state) => ({
      currentBook: {
        ...state.currentBook,
        dimensions: {
          ...state.currentBook.dimensions,
          ...dims,
        },
      },
    }));
  },

  validateCurrentBook: async () => {
    try {
      const res = await apiRequest<{ valid: boolean; errors: Record<string, string> }>(
        "/api/books/validate",
        {
          method: "POST",
          body: JSON.stringify({ book: get().currentBook }),
        }
      );
      set({ validationErrors: res.errors || {} });
      return res.valid;
    } catch {
      return false;
    }
  },

  saveCurrentBook: async () => {
    set({ isSaving: true, saveMessage: null });
    try {
      const res = await apiRequest<{ success: boolean; errors?: Record<string, string> }>(
        "/api/books/save",
        {
          method: "POST",
          body: JSON.stringify({
            book: get().currentBook,
            skip_validation: false,
          }),
        }
      );

      if (res.success) {
        set({
          isSaving: false,
          saveMessage: "Книга успешно сохранена и поставлена в очередь Ozon!",
          validationErrors: {},
        });
        return { success: true };
      } else {
        set({
          isSaving: false,
          validationErrors: res.errors || {},
        });
        return { success: false, errors: res.errors };
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      set({ isSaving: false, saveMessage: `Ошибка: ${msg}` });
      return { success: false };
    }
  },

  reopenBook: async (article: string) => {
    try {
      const res = await apiRequest<{ book: BookData; tab: WorkspaceTab }>(
        "/api/books/reopen",
        {
          method: "POST",
          body: JSON.stringify({ article }),
        }
      );

      set((state) => {
        const existingTab = state.tabs.find((t) => t.id === res.tab.id);
        const tabs = existingTab
          ? state.tabs.map((t) => ({ ...t, is_active: t.id === res.tab.id }))
          : [...state.tabs.map((t) => ({ ...t, is_active: false })), res.tab];

        return {
          tabs,
          activeTabId: res.tab.id,
          currentBook: res.book,
          validationErrors: {},
        };
      });
    } catch (err) {
      console.error("Failed to reopen book:", err);
      throw err;
    }
  },
}));

// Setup SSE listener for opened tabs
sseClient.on("tab.opened", (payload) => {
  if (payload?.tab_id && payload?.article) {
    const store = useWorkspaceStore.getState();
    const existing = store.tabs.find((t) => t.id === payload.tab_id);
    if (!existing) {
      store.reopenBook(payload.article);
    }
  }
});
