/**
 * IndexedDB persistence layer for Mobile Studio PWA.
 *
 * Implements ADR-9 (local offline storage surviving iOS Safari tab suspension).
 */

import { openDB, type DBSchema, type IDBPDatabase } from "idb";

export interface MobileBook {
  id: string;
  name: string;
  createdAt: number;
}

export interface MobilePhoto {
  id: string;
  bookId: string;
  blob: Blob;
  role: string;
  order: number;
  createdAt: number;
}

interface MobileStudioDB extends DBSchema {
  books: {
    key: string;
    value: MobileBook;
    indexes: { "by-created": number };
  };
  photos: {
    key: string;
    value: MobilePhoto;
    indexes: { "by-book": string; "by-created": number };
  };
}

const DB_NAME = "bookinistic_mobile_pwa";
const DB_VERSION = 1;

let dbPromise: Promise<IDBPDatabase<MobileStudioDB>> | null = null;

export function getMobileDb(): Promise<IDBPDatabase<MobileStudioDB>> {
  if (!dbPromise) {
    dbPromise = openDB<MobileStudioDB>(DB_NAME, DB_VERSION, {
      upgrade(db) {
        if (!db.objectStoreNames.contains("books")) {
          const bookStore = db.createObjectStore("books", { keyPath: "id" });
          bookStore.createIndex("by-created", "createdAt");
        }
        if (!db.objectStoreNames.contains("photos")) {
          const photoStore = db.createObjectStore("photos", { keyPath: "id" });
          photoStore.createIndex("by-book", "bookId");
          photoStore.createIndex("by-created", "createdAt");
        }
      },
    });
  }
  return dbPromise;
}

export async function createMobileBook(name?: string): Promise<MobileBook> {
  const db = await getMobileDb();
  const id = `book_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`;
  const bookCount = (await db.count("books")) + 1;
  const book: MobileBook = {
    id,
    name: name || `Книга #${bookCount}`,
    createdAt: Date.now(),
  };
  await db.put("books", book);
  return book;
}

export async function listMobileBooks(): Promise<MobileBook[]> {
  const db = await getMobileDb();
  return db.getAllFromIndex("books", "by-created");
}

export async function deleteMobileBook(bookId: string): Promise<void> {
  const db = await getMobileDb();
  const tx = db.transaction(["books", "photos"], "readwrite");
  await tx.objectStore("books").delete(bookId);

  const photoIndex = tx.objectStore("photos").index("by-book");
  let cursor = await photoIndex.openCursor(bookId);
  while (cursor) {
    await cursor.delete();
    cursor = await cursor.continue();
  }
  await tx.done;
}

export async function saveMobilePhoto(
  bookId: string,
  blob: Blob,
  role: string = "cover_front",
  order: number = 0
): Promise<MobilePhoto> {
  const db = await getMobileDb();
  const photo: MobilePhoto = {
    id: `photo_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
    bookId,
    blob,
    role,
    order,
    createdAt: Date.now(),
  };
  await db.put("photos", photo);
  return photo;
}

export async function listMobilePhotos(bookId: string): Promise<MobilePhoto[]> {
  const db = await getMobileDb();
  const photos = await db.getAllFromIndex("photos", "by-book", bookId);
  return photos.sort((a, b) => a.order - b.order || a.createdAt - b.createdAt);
}

export async function updatePhotoRole(photoId: string, role: string): Promise<void> {
  const db = await getMobileDb();
  const photo = await db.get("photos", photoId);
  if (photo) {
    photo.role = role;
    await db.put("photos", photo);
  }
}

export async function deleteMobilePhoto(photoId: string): Promise<void> {
  const db = await getMobileDb();
  await db.delete("photos", photoId);
}

export async function clearAllMobileData(): Promise<void> {
  const db = await getMobileDb();
  const tx = db.transaction(["books", "photos"], "readwrite");
  await tx.objectStore("books").clear();
  await tx.objectStore("photos").clear();
  await tx.done;
}
