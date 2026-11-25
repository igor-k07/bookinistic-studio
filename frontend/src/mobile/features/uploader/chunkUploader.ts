/**
 * Chunked idempotent uploader for Mobile Studio.
 *
 * Implements ADR-9 / Step 7.2:
 * Uploads photos in chunks of 2 with X-Mobile-Token, 3x exponential retry,
 * mutation lock, and wipes IndexedDB only after commit acknowledgement.
 */

import { apiRequest } from "../../../api/client";
import {
  listMobilePhotos,
  clearAllMobileData,
  type MobileBook,
} from "../../db/mobileDb";

export interface UploadProgress {
  totalPhotos: number;
  uploadedPhotos: number;
  percentage: number;
  status: "idle" | "uploading" | "committing" | "completed" | "error";
  errorMessage?: string;
}

export type ProgressCallback = (progress: UploadProgress) => void;

let isUploadLocked = false;

export function isUploadingActive(): boolean {
  return isUploadLocked;
}

export async function uploadMobileBooksSession(
  sessionId: string,
  token: string,
  books: MobileBook[],
  onProgress?: ProgressCallback
): Promise<{ success: boolean; createdAssetIds: string[] }> {
  if (isUploadLocked) {
    throw new Error("Upload already in progress");
  }
  isUploadLocked = true;

  try {
    // 1. Gather all photos across books
    const bookPhotoPairs: { bookIndex: number; photoBlob: Blob; role: string; photoId: string }[] = [];
    for (let bIdx = 0; bIdx < books.length; bIdx++) {
      const photos = await listMobilePhotos(books[bIdx].id);
      for (const p of photos) {
        bookPhotoPairs.push({
          bookIndex: bIdx,
          photoBlob: p.blob,
          role: p.role,
          photoId: p.id,
        });
      }
    }

    const total = bookPhotoPairs.length;
    if (total === 0) {
      onProgress?.({
        totalPhotos: 0,
        uploadedPhotos: 0,
        percentage: 100,
        status: "completed",
      });
      return { success: true, createdAssetIds: [] };
    }

    onProgress?.({
      totalPhotos: total,
      uploadedPhotos: 0,
      percentage: 0,
      status: "uploading",
    });

    // 2. Upload chunks of 2 photos sequentially
    const CHUNK_SIZE = 2;
    let uploadedCount = 0;

    for (let i = 0; i < total; i += CHUNK_SIZE) {
      const slice = bookPhotoPairs.slice(i, i + CHUNK_SIZE);

      for (let sIdx = 0; sIdx < slice.length; sIdx++) {
        const item = slice[sIdx];
        const chunkIndex = i + sIdx;

        await uploadSingleChunkWithRetry(
          sessionId,
          token,
          item.photoBlob,
          chunkIndex,
          item.role,
          item.bookIndex
        );

        uploadedCount++;
        const pct = Math.round((uploadedCount / total) * 90); // 0-90% during chunk uploads
        onProgress?.({
          totalPhotos: total,
          uploadedPhotos: uploadedCount,
          percentage: pct,
          status: "uploading",
        });
      }
    }

    // 3. Commit session on backend
    onProgress?.({
      totalPhotos: total,
      uploadedPhotos: uploadedCount,
      percentage: 95,
      status: "committing",
    });

    const commitResult = await apiRequest<{
      status: string;
      session_id: string;
      assets_count: number;
      asset_ids: string[];
    }>("/api/mobile/commit", {
      method: "POST",
      headers: {
        "X-Mobile-Token": token,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        session_id: sessionId,
      }),
    });

    if (commitResult.status !== "committed") {
      throw new Error(`Commit failed with status: ${commitResult.status}`);
    }

    // 4. Wipe local IndexedDB only AFTER confirmed commit
    await clearAllMobileData();

    // Haptic feedback for successful commit
    if (typeof navigator !== "undefined" && "vibrate" in navigator) {
      navigator.vibrate([60, 50, 100]);
    }

    onProgress?.({
      totalPhotos: total,
      uploadedPhotos: total,
      percentage: 100,
      status: "completed",
    });

    return {
      success: true,
      createdAssetIds: commitResult.asset_ids || [],
    };
  } catch (err: unknown) {
    const errorMsg = err instanceof Error ? err.message : String(err);
    onProgress?.({
      totalPhotos: 0,
      uploadedPhotos: 0,
      percentage: 0,
      status: "error",
      errorMessage: errorMsg,
    });
    throw err;
  } finally {
    isUploadLocked = false;
  }
}

async function uploadSingleChunkWithRetry(
  sessionId: string,
  token: string,
  blob: Blob,
  chunkIndex: number,
  role: string,
  bookIndex: number,
  maxRetries: number = 3
): Promise<void> {
  let attempt = 0;
  let lastError: unknown = null;

  while (attempt < maxRetries) {
    attempt++;
    const formData = new FormData();
    formData.append("file", blob, `photo_${chunkIndex}.jpg`);
    formData.append("session_id", sessionId);
    formData.append("chunk_index", String(chunkIndex));
    formData.append("role", role);
    formData.append("book_index", String(bookIndex));

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 20000); // 20s timeout

    try {
      const response = await fetch("/api/mobile/upload-chunk", {
        method: "POST",
        headers: {
          "X-Mobile-Token": token,
        },
        body: formData,
        signal: controller.signal,
      });

      clearTimeout(timeout);

      if (response.ok) {
        return; // Success!
      }
      const errText = await response.text();
      lastError = new Error(`Server returned ${response.status}: ${errText}`);
    } catch (e) {
      clearTimeout(timeout);
      lastError = e;
    }

    // Exponential backoff: 300ms, 600ms, 1200ms
    if (attempt < maxRetries) {
      await new Promise((res) => setTimeout(res, 300 * Math.pow(2, attempt - 1)));
    }
  }

  throw lastError || new Error(`Upload failed for chunk ${chunkIndex} after ${maxRetries} attempts`);
}
