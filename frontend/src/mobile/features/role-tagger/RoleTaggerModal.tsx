import React, { useEffect, useState } from "react";
import type { MobilePhoto } from "../../db/mobileDb";

export interface RoleOption {
  key: string;
  label: string;
  icon: string;
  shortcut: string;
}

export const STANDARD_ROLES: RoleOption[] = [
  { key: "cover_front", label: "Обложка (лицо)", icon: "📖", shortcut: "1" },
  { key: "cover_back", label: "Обложка (зад/штрихкод)", icon: "🏷️", shortcut: "2" },
  { key: "info_pages", label: "Титул / Выходные данные", icon: "📄", shortcut: "3" },
  { key: "mantra_defects", label: "Корешок / Дефекты", icon: "🔍", shortcut: "4" },
  { key: "illustrations", label: "Иллюстрации / Разворот", icon: "🎨", shortcut: "5" },
];

interface Props {
  photos: MobilePhoto[];
  initialIndex?: number;
  onSelectRole: (photoId: string, role: string) => Promise<void>;
  onClose: () => void;
}

export function RoleTaggerModal({
  photos,
  initialIndex = 0,
  onSelectRole,
  onClose,
}: Props): React.JSX.Element | null {
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  const currentPhoto = photos[currentIndex];

  useEffect(() => {
    if (!currentPhoto) {
      setPreviewUrl(null);
      return;
    }
    const url = URL.createObjectURL(currentPhoto.blob);
    setPreviewUrl(url);

    return () => {
      URL.revokeObjectURL(url);
    };
  }, [currentPhoto]);

  if (!currentPhoto) {
    return null;
  }

  const handleRoleTap = async (roleKey: string) => {
    // Haptic feedback
    if (typeof navigator !== "undefined" && "vibrate" in navigator) {
      navigator.vibrate(40);
    }

    await onSelectRole(currentPhoto.id, roleKey);

    // Instant advance
    if (currentIndex < photos.length - 1) {
      setCurrentIndex((prev) => prev + 1);
    } else {
      onClose();
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-slate-950 text-slate-100">
      {/* Top Header */}
      <div className="flex h-14 items-center justify-between border-b border-slate-800 px-4">
        <span className="text-sm font-medium text-slate-300">
          Фото {currentIndex + 1} из {photos.length}
        </span>
        <button
          onClick={onClose}
          className="rounded-lg bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 active:bg-slate-700"
        >
          Готово
        </button>
      </div>

      {/* Main Photo Preview */}
      <div className="relative flex flex-1 items-center justify-center overflow-hidden p-4">
        {previewUrl && (
          <img
            src={previewUrl}
            alt="Current capture"
            className="max-h-full max-w-full rounded-lg object-contain shadow-2xl"
          />
        )}
        <div className="absolute top-6 left-6 rounded-md bg-slate-900/80 px-2.5 py-1 text-xs font-medium text-emerald-400 backdrop-blur-sm">
          Текущая роль: {STANDARD_ROLES.find((r) => r.key === currentPhoto.role)?.label || currentPhoto.role}
        </div>
      </div>

      {/* Bottom Express Role Buttons (1-Tap) */}
      <div className="grid grid-cols-1 gap-2 border-t border-slate-800 bg-slate-900/90 p-4 pb-8 backdrop-blur-md">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {STANDARD_ROLES.map((role) => {
            const isSelected = currentPhoto.role === role.key;
            return (
              <button
                key={role.key}
                onClick={() => handleRoleTap(role.key)}
                className={`flex items-center gap-2 rounded-xl p-3 text-left transition-all active:scale-95 ${
                  isSelected
                    ? "bg-emerald-600 font-semibold text-white ring-2 ring-emerald-400"
                    : "bg-slate-800 text-slate-200 active:bg-slate-700"
                }`}
              >
                <span className="text-xl">{role.icon}</span>
                <span className="text-xs leading-tight">{role.label}</span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

