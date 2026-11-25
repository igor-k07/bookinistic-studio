import { describe, it, expect, beforeEach, vi } from "vitest";
import "fake-indexeddb/auto";
import {
  createMobileBook,
  saveMobilePhoto,
  clearAllMobileData,
  listMobilePhotos,
} from "../db/mobileDb";
import { uploadMobileBooksSession } from "../features/uploader/chunkUploader";

describe("chunkUploader", () => {
  beforeEach(async () => {
    await clearAllMobileData();
    vi.restoreAllMocks();
  });

  it("uploads photos in chunks and commits session", async () => {
    const book = await createMobileBook("Upload Test Book");
    const blob1 = new Blob(["chunk1-data"], { type: "image/jpeg" });
    const blob2 = new Blob(["chunk2-data"], { type: "image/jpeg" });

    await saveMobilePhoto(book.id, blob1, "cover_front", 0);
    await saveMobilePhoto(book.id, blob2, "title_page", 1);

    const uploadedUrls: string[] = [];

    // Mock fetch for upload-chunk and commit
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      uploadedUrls.push(url);
      if (url.includes("/api/mobile/upload-chunk")) {
        return {
          ok: true,
          status: 200,
          text: async () => JSON.stringify({ status: "ok" }),
          json: async () => ({ status: "ok" }),
        };
      }
      if (url.includes("/api/mobile/commit")) {
        return {
          ok: true,
          status: 200,
          headers: new Headers({ "content-type": "application/json" }),
          json: async () => ({
            status: "committed",
            session_id: "test_session_1",
            assets_count: 2,
            asset_ids: ["asset_1", "asset_2"],
          }),
        };
      }
      return { ok: false, status: 404 };
    });

    const progressReports: number[] = [];
    const result = await uploadMobileBooksSession(
      "test_session_1",
      "token_xyz",
      [book],
      (p) => progressReports.push(p.percentage)
    );

    expect(result.success).toBe(true);
    expect(result.createdAssetIds).toEqual(["asset_1", "asset_2"]);

    // Verify 2 chunk uploads and 1 commit
    expect(uploadedUrls.filter((u) => u.includes("upload-chunk"))).toHaveLength(2);
    expect(uploadedUrls.filter((u) => u.includes("commit"))).toHaveLength(1);

    // Verify progress reached 100%
    expect(progressReports).toContain(100);

    // Verify local IndexedDB was wiped after confirmed commit
    const remainingPhotos = await listMobilePhotos(book.id);
    expect(remainingPhotos).toHaveLength(0);
  });
});
