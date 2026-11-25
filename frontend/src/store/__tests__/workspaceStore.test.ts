import { describe, it, expect, vi, beforeEach } from "vitest";
import { useWorkspaceStore } from "../workspaceStore";

// Mock apiRequest
vi.mock("../../api/client", () => ({
  apiRequest: vi.fn(async (url: string, options?: RequestInit) => {
    if (url.startsWith("/api/tabs") && options?.method === "POST") {
      const payload = JSON.parse(options.body as string);
      return payload;
    }
    if (url.startsWith("/api/tabs") && options?.method === "PATCH") {
      return { success: true };
    }
    if (url.startsWith("/api/tabs") && options?.method === "DELETE") {
      return { success: true };
    }
    if (url.startsWith("/api/books/validate")) {
      return { valid: true, errors: {} };
    }
    if (url.startsWith("/api/books") && options?.method === "POST") {
      const payload = JSON.parse(options.body as string);
      return payload;
    }
    return {};
  }),
}));

describe("workspaceStore", () => {
  beforeEach(() => {
    // Reset store state
    useWorkspaceStore.setState({
      tabs: [],
      activeTabId: null,
      currentBook: {
        article: "TEST-01",
        title: "Test Title",
        author: "Test Author",
        year: 1980,
        price: 500,
        old_price: null,
        template_mode: "pre2011",
        status: "DRAFT",
        storage_location: "A1",
        publisher: "Наука",
        series: "",
        isbn: "",
        format_code: "84×108/32",
        pages: 200,
        cover_type: "Твердый переплет",
        condition: "Хорошая",
        annotation: "",
        brand: "Наука",
        author_cover: "",
        original_title: "",
        barcode: "",
        genre: "Наука",
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
      },
      validationErrors: {},
      isSaving: false,
      saveMessage: null,
    });
  });

  it("updates field and tracks USER_MANUAL provenance (priority 5)", () => {
    const store = useWorkspaceStore.getState();
    store.updateBookField("title", "New Great Book");

    const updated = useWorkspaceStore.getState().currentBook;
    expect(updated.title).toBe("New Great Book");
    expect(updated.field_sources["title"]).toBe(5);
  });

  it("automatically switches era boundary: year <= 2010 -> pre2011, year >= 2011 -> post2011", () => {
    const store = useWorkspaceStore.getState();

    // 1995 -> pre2011
    store.updateBookField("year", 1995);
    expect(useWorkspaceStore.getState().currentBook.template_mode).toBe("pre2011");

    // 2010 -> pre2011
    store.updateBookField("year", 2010);
    expect(useWorkspaceStore.getState().currentBook.template_mode).toBe("pre2011");

    // 2011 -> post2011
    store.updateBookField("year", 2011);
    expect(useWorkspaceStore.getState().currentBook.template_mode).toBe("post2011");

    // 2024 -> post2011
    store.updateBookField("year", 2024);
    expect(useWorkspaceStore.getState().currentBook.template_mode).toBe("post2011");
  });

  it("updates book dimensions properly", () => {
    const store = useWorkspaceStore.getState();
    store.updateDimensions({ width_mm: 145, length_mm: 215, height_mm: 22 });

    const dims = useWorkspaceStore.getState().currentBook.dimensions;
    expect(dims.width_mm).toBe(145);
    expect(dims.length_mm).toBe(215);
    expect(dims.height_mm).toBe(22);
  });

  it("creates a tab and sets it active", async () => {
    const store = useWorkspaceStore.getState();
    await store.createTab("DP-B-12345", "Новая книга 12345");

    const state = useWorkspaceStore.getState();
    expect(state.tabs.length).toBe(1);
    expect(state.tabs[0].book_article).toBe("DP-B-12345");
    expect(state.tabs[0].is_active).toBe(true);
    expect(state.activeTabId).toBe(state.tabs[0].id);
  });
});
