import { describe, it, expect, beforeEach, vi } from "vitest";
import { apiRequest, ApiError, setSessionToken, getSessionToken } from "../client";
import { SSEClient } from "../sse";

describe("apiClient", () => {
  beforeEach(() => {
    setSessionToken(null);
    vi.restoreAllMocks();
  });

  it("handles session token getting and setting", () => {
    expect(getSessionToken()).toBeNull();
    setSessionToken("secret-token-123");
    expect(getSessionToken()).toBe("secret-token-123");
  });

  it("adds X-Mobile-Token header when session token is set", async () => {
    setSessionToken("test-token-abc");

    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ status: "ok" }),
    });
    global.fetch = mockFetch;

    const res = await apiRequest<{ status: string }>("/api/health");
    expect(res).toEqual({ status: "ok" });
    expect(mockFetch).toHaveBeenCalledWith(
      "/api/health",
      expect.objectContaining({
        headers: expect.objectContaining({
          "X-Mobile-Token": "test-token-abc",
        }),
      })
    );
  });

  it("throws structured ApiError on non-200 responses", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 404,
      statusText: "Not Found",
      headers: new Headers({ "content-type": "application/json" }),
      json: async () => ({ detail: "Book not found" }),
    });

    await expect(apiRequest("/api/books/missing")).rejects.toThrow(ApiError);
    await expect(apiRequest("/api/books/missing")).rejects.toThrow("Book not found");
  });
});

describe("SSEClient", () => {
  it("subscribes and emits events to registered handlers", () => {
    const sse = new SSEClient("/api/mock-events");
    const received: unknown[] = [];

    const unsubscribe = sse.on("store.switched", (data) => {
      received.push(data);
    });

    // Simulate internal emit
    // @ts-expect-error accessing private method for unit test
    sse.emit("store.switched", { active_store: "store_99" });

    expect(received).toHaveLength(1);
    expect(received[0]).toEqual({ active_store: "store_99" });

    // Unsubscribe and verify no more events
    unsubscribe();
    // @ts-expect-error accessing private method for unit test
    sse.emit("store.switched", { active_store: "store_100" });
    expect(received).toHaveLength(1);
  });
});

