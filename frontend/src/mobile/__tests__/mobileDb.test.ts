import { describe, it, expect, beforeEach } from "vitest";
import "fake-indexeddb/auto";
import {
  createMobileBook,
  listMobileBooks,
  saveMobilePhoto,
  listMobilePhotos,
  updatePhotoRole,
  deleteMobilePhoto,
  deleteMobileBook,
  clearAllMobileData,
} from "../db/mobileDb";

describe("mobileDb IndexedDB persistence", () => {
  beforeEach(async () => {
    await clearAllMobileData();
  });

  it("creates and lists books", async () => {
    const book1 = await createMobileBook("Book A");
    const book2 = await createMobileBook("Book B");

    const list = await listMobileBooks();
    expect(list).toHaveLength(2);
    expect(list.map((b) => b.id)).toContain(book1.id);
    expect(list.map((b) => b.id)).toContain(book2.id);
  });

  it("saves, lists, updates role, and deletes photos", async () => {
    const book = await createMobileBook("Test Book");
    const blob = new Blob(["fake-image-bytes"], { type: "image/jpeg" });

    const photo = await saveMobilePhoto(book.id, blob, "cover_front", 0);
    expect(photo.role).toBe("cover_front");
    expect(photo.bookId).toBe(book.id);

    let photos = await listMobilePhotos(book.id);
    expect(photos).toHaveLength(1);

    await updatePhotoRole(photo.id, "info_pages");
    photos = await listMobilePhotos(book.id);
    expect(photos[0].role).toBe("info_pages");

    await deleteMobilePhoto(photo.id);
    photos = await listMobilePhotos(book.id);
    expect(photos).toHaveLength(0);
  });

  it("cascades photo deletion when book is deleted", async () => {
    const book = await createMobileBook("Cascade Book");
    const blob = new Blob(["dummy"], { type: "image/jpeg" });
    await saveMobilePhoto(book.id, blob, "cover_front", 0);

    let photos = await listMobilePhotos(book.id);
    expect(photos).toHaveLength(1);

    await deleteMobileBook(book.id);
    const books = await listMobileBooks();
    expect(books.find((b) => b.id === book.id)).toBeUndefined();

    photos = await listMobilePhotos(book.id);
    expect(photos).toHaveLength(0);
  });
});
