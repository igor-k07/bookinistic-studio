import React, { useEffect, useRef, useState } from "react";
import { setSessionToken } from "../api/client";
import {
  createMobileBook,
  deleteMobileBook,
  deleteMobilePhoto,
  listMobileBooks,
  listMobilePhotos,
  saveMobilePhoto,
  updatePhotoRole,
  type MobileBook,
  type MobilePhoto,
} from "./db/mobileDb";
import { processAndResizePhoto } from "./features/capture/imageProcessor";
import { RoleTaggerModal, STANDARD_ROLES } from "./features/role-tagger/RoleTaggerModal";
import {
  isUploadingActive,
  uploadMobileBooksSession,
  type UploadProgress,
} from "./features/uploader/chunkUploader";

export default function MobileApp(): React.JSX.Element {
  const [token, setToken] = useState<string>("");
  const [sessionId] = useState<string>(() => `mob_${Date.now()}_${Math.random().toString(36).substring(2, 7)}`);
  const [books, setBooks] = useState<MobileBook[]>([]);
  const [activeBookId, setActiveBookId] = useState<string>("");
  const [photos, setPhotos] = useState<MobilePhoto[]>([]);
  const [taggerIndex, setTaggerIndex] = useState<number | null>(null);
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [uploadProgress, setUploadProgress] = useState<UploadProgress | null>(null);

  const cameraInputRef = useRef<HTMLInputElement>(null);
  const galleryInputRef = useRef<HTMLInputElement>(null);

  // 1. Token Initialization
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const urlToken = params.get("token") || localStorage.getItem("mobile_token") || "";
    if (urlToken) {
      setToken(urlToken);
      setSessionToken(urlToken);
      localStorage.setItem("mobile_token", urlToken);
    }
    loadBooks();
  }, []);

  // 2. Load books from IndexedDB
  const loadBooks = async () => {
    let existingBooks = await listMobileBooks();
    if (existingBooks.length === 0) {
      const firstBook = await createMobileBook("Книга #1");
      existingBooks = [firstBook];
    }
    setBooks(existingBooks);
    const currentActive = existingBooks.find((b) => b.id === activeBookId) ? activeBookId : existingBooks[0].id;
    setActiveBookId(currentActive);
    loadPhotos(currentActive);
  };

  // 3. Load photos for active book
  const loadPhotos = async (bookId: string) => {
    if (!bookId) return;
    const loaded = await listMobilePhotos(bookId);
    setPhotos(loaded);
  };

  const handleSelectBook = (bookId: string) => {
    setActiveBookId(bookId);
    loadPhotos(bookId);
  };

  const handleAddNextBook = async () => {
    const newBook = await createMobileBook();
    setBooks((prev) => [...prev, newBook]);
    setActiveBookId(newBook.id);
    setPhotos([]);
  };

  const handleDeleteBook = async (bookId: string) => {
    if (books.length <= 1) return;
    await deleteMobileBook(bookId);
    loadBooks();
  };

  // 4. Photo Capture / Selection
  const handleFilesSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0 || !activeBookId) return;

    setIsProcessing(true);
    try {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        // Resize to 1600px with memory cleanup
        const resizedBlob = await processAndResizePhoto(file, 1600, 0.82);
        // Default role heuristic: 1st is cover_front, 2nd is title_page, rest are info_pages
        const currentCount = photos.length + i;
        const defaultRole =
          currentCount === 0
            ? "cover_front"
            : currentCount === 1
            ? "info_pages"
            : currentCount === 2
            ? "cover_back"
            : "info_pages";

        await saveMobilePhoto(activeBookId, resizedBlob, defaultRole, currentCount);
      }
      await loadPhotos(activeBookId);
    } catch (err) {
      console.error("Error processing captured photos:", err);
      alert("Ошибка при обработке фото");
    } finally {
      setIsProcessing(false);
      if (e.target) e.target.value = "";
    }
  };

  // 5. Upload & Commit Session
  const handleUploadAll = async () => {
    if (!token) {
      alert("Требуется авторизация! Отсканируйте QR-код с экрана компьютера.");
      return;
    }
    if (isUploadingActive()) return;

    try {
      await uploadMobileBooksSession(sessionId, token, books, (progress) => {
        setUploadProgress(progress);
      });
      alert("Все книги успешно выгружены в Studio!");
      loadBooks();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      alert(`Ошибка при выгрузке: ${msg}`);
    }
  };

  return (
    <div className="flex h-screen w-screen flex-col bg-slate-950 text-slate-100 select-none pb-safe">
      {/* Top Header */}
      <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-800 bg-slate-900/80 px-4 backdrop-blur-md">
        <div className="flex items-center gap-2">
          <span className="text-base font-bold tracking-tight text-white">
            Bookinistic <span className="text-emerald-400">Mobile</span>
          </span>
          <span
            className={`h-2.5 w-2.5 rounded-full ${
              token ? "bg-emerald-500 shadow-sm shadow-emerald-500/50" : "bg-amber-500"
            }`}
            title={token ? "Токен активен" : "Токен отсутствует"}
          />
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleAddNextBook}
            className="flex items-center gap-1 rounded-lg bg-emerald-600/90 px-3 py-1.5 text-xs font-semibold text-white shadow-sm active:scale-95"
          >
            + След. книга
          </button>
        </div>
      </header>

      {/* Book Tabs Navigation */}
      <nav className="flex shrink-0 items-center gap-2 overflow-x-auto border-b border-slate-800 bg-slate-900/40 px-3 py-2 scrollbar-none">
        {books.map((b) => (
          <div
            key={b.id}
            onClick={() => handleSelectBook(b.id)}
            className={`flex items-center gap-2 whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
              b.id === activeBookId
                ? "bg-emerald-600 text-white shadow"
                : "bg-slate-800/80 text-slate-300 active:bg-slate-700"
            }`}
          >
            <span>{b.name}</span>
            {books.length > 1 && (
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  handleDeleteBook(b.id);
                }}
                className="text-slate-400 hover:text-red-400"
              >
                ✕
              </button>
            )}
          </div>
        ))}
      </nav>

      {/* Photos Grid Area */}
      <main className="flex-1 overflow-y-auto p-4">
        {photos.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center text-slate-500">
            <span className="text-4xl">📷</span>
            <p className="mt-2 text-sm font-medium text-slate-400">
              В этой книге пока нет фотографий
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Нажмите «Камера» или «Галерея» внизу экрана
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4">
            {photos.map((p, idx) => {
              const url = URL.createObjectURL(p.blob);
              const roleMeta = STANDARD_ROLES.find((r) => r.key === p.role);
              return (
                <div
                  key={p.id}
                  onClick={() => setTaggerIndex(idx)}
                  className="group relative flex aspect-[3/4] flex-col overflow-hidden rounded-xl border border-slate-800 bg-slate-900 shadow-sm active:scale-95 transition-transform"
                >
                  <img
                    src={url}
                    alt={p.role}
                    onLoad={() => URL.revokeObjectURL(url)}
                    className="h-full w-full object-cover"
                  />
                  <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-slate-950/90 via-slate-950/60 to-transparent p-2">
                    <span className="block truncate text-[11px] font-semibold text-emerald-300">
                      {roleMeta?.icon} {roleMeta?.label || p.role}
                    </span>
                  </div>
                  <button
                    onClick={async (e) => {
                      e.stopPropagation();
                      await deleteMobilePhoto(p.id);
                      loadPhotos(activeBookId);
                    }}
                    className="absolute top-1.5 right-1.5 flex h-6 w-6 items-center justify-center rounded-full bg-slate-900/80 text-xs text-slate-300 active:bg-red-600 active:text-white"
                  >
                    ✕
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </main>

      {/* Upload Progress Bar if active */}
      {uploadProgress && (
        <div className="border-t border-slate-800 bg-slate-900 px-4 py-2">
          <div className="flex items-center justify-between text-xs text-slate-300">
            <span>
              {uploadProgress.status === "uploading" && "Выгрузка фотографий..."}
              {uploadProgress.status === "committing" && "Сохранение сессии..."}
              {uploadProgress.status === "completed" && "Выгрузка завершена!"}
              {uploadProgress.status === "error" && "Ошибка при выгрузке"}
            </span>
            <span className="font-semibold text-emerald-400">
              {uploadProgress.percentage}%
            </span>
          </div>
          <div className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className={`h-full transition-all duration-300 ${
                uploadProgress.status === "error" ? "bg-red-500" : "bg-emerald-500"
              }`}
              style={{ width: `${uploadProgress.percentage}%` }}
            />
          </div>
        </div>
      )}

      {/* Bottom Sticky Action Bar */}
      <footer className="grid grid-cols-3 gap-2 border-t border-slate-800 bg-slate-900/90 p-3 backdrop-blur-md">
        {/* Hidden File Inputs */}
        <input
          ref={cameraInputRef}
          type="file"
          accept="image/*"
          capture="environment"
          onChange={handleFilesSelected}
          className="hidden"
        />
        <input
          ref={galleryInputRef}
          type="file"
          accept="image/*"
          multiple
          onChange={handleFilesSelected}
          className="hidden"
        />

        <button
          disabled={isProcessing}
          onClick={() => cameraInputRef.current?.click()}
          className="flex flex-col items-center justify-center rounded-xl bg-slate-800 py-2.5 text-xs font-semibold text-slate-200 active:bg-slate-700 disabled:opacity-50"
        >
          <span className="text-xl">📷</span>
          <span>Камера</span>
        </button>

        <button
          disabled={isProcessing}
          onClick={() => galleryInputRef.current?.click()}
          className="flex flex-col items-center justify-center rounded-xl bg-slate-800 py-2.5 text-xs font-semibold text-slate-200 active:bg-slate-700 disabled:opacity-50"
        >
          <span className="text-xl">🖼️</span>
          <span>Галерея</span>
        </button>

        <button
          disabled={photos.length === 0 || isProcessing || isUploadingActive()}
          onClick={handleUploadAll}
          className="flex flex-col items-center justify-center rounded-xl bg-emerald-600 py-2.5 text-xs font-semibold text-white shadow-md active:bg-emerald-700 disabled:opacity-40"
        >
          <span className="text-xl">🚀</span>
          <span>В студию ({photos.length})</span>
        </button>
      </footer>

      {/* Role Tagger Modal */}
      {taggerIndex !== null && (
        <RoleTaggerModal
          photos={photos}
          initialIndex={taggerIndex}
          onSelectRole={async (photoId, role) => {
            await updatePhotoRole(photoId, role);
            await loadPhotos(activeBookId);
          }}
          onClose={() => setTaggerIndex(null)}
        />
      )}
    </div>
  );
}
