/**
 * Mobile client-side image downscaler and memory optimizer.
 *
 * Implements ADR-9 / Step 7.2:
 * Resize via createImageBitmap -> 1600px JPEG Q0.82 with canvas.width = 0 cleanup.
 */

export async function processAndResizePhoto(
  fileOrBlob: File | Blob,
  maxDimension: number = 1600,
  quality: number = 0.82
): Promise<Blob> {
  let bitmap: ImageBitmap | HTMLImageElement | null = null;
  let objectUrlToRevoke: string | null = null;

  try {
    if (typeof createImageBitmap === "function") {
      try {
        bitmap = await createImageBitmap(fileOrBlob);
      } catch {
        // Fallback to Image element if createImageBitmap fails
      }
    }

    if (!bitmap) {
      objectUrlToRevoke = URL.createObjectURL(fileOrBlob);
      const img = new Image();
      img.src = objectUrlToRevoke;
      await new Promise<void>((resolve, reject) => {
        img.onload = () => resolve();
        img.onerror = (e) => reject(new Error(`Failed to load image: ${e}`));
      });
      bitmap = img;
    }

    const origWidth = "width" in bitmap ? bitmap.width : 0;
    const origHeight = "height" in bitmap ? bitmap.height : 0;

    let targetWidth = origWidth;
    let targetHeight = origHeight;

    if (origWidth > maxDimension || origHeight > maxDimension) {
      if (origWidth >= origHeight) {
        targetWidth = maxDimension;
        targetHeight = Math.round((origHeight * maxDimension) / origWidth);
      } else {
        targetHeight = maxDimension;
        targetWidth = Math.round((origWidth * maxDimension) / origHeight);
      }
    }

    const canvas = document.createElement("canvas");
    canvas.width = Math.max(1, targetWidth);
    canvas.height = Math.max(1, targetHeight);

    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) {
      throw new Error("Could not acquire 2D canvas context");
    }

    ctx.drawImage(bitmap, 0, 0, targetWidth, targetHeight);

    const resizedBlob = await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (b) => {
          if (b) {
            resolve(b);
          } else {
            reject(new Error("Canvas toBlob failed"));
          }
        },
        "image/jpeg",
        quality
      );
    });

    // iOS WebKit memory leak defense: release canvas backing buffer immediately
    canvas.width = 0;
    canvas.height = 0;

    return resizedBlob;
  } finally {
    if (bitmap && "close" in bitmap && typeof bitmap.close === "function") {
      bitmap.close();
    }
    if (objectUrlToRevoke) {
      URL.revokeObjectURL(objectUrlToRevoke);
    }
  }
}

