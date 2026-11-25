/**
 * StudioEngine — Isolated TypeScript class encapsulating Cropper.js and image adjustments.
 *
 * Conforms to Architectural Guardrail 10:
 * Encapsulates Cropper.js inside an isolated class with guaranteed destroy() cleanup.
 */

import Cropper from "cropperjs";
import {
  DEFAULT_STUDIO_TRANSFORM,
  type StudioCropBox,
  type StudioFilters,
  type StudioTransformState,
} from "./HistoryStack";

export type CropRatio = "3:4" | "free";

export interface PresetDefinition {
  name: string;
  description: string;
  filters: Partial<StudioFilters>;
}

export const STUDIO_PRESETS: Record<string, PresetDefinition> = {
  auto: {
    name: "⚡ Авто-баланс",
    description: "Мягкое осветление и четкость шрифта",
    filters: { brightness: 5, contrast: 15, sharpness: 12, whiten: 15 },
  },
  vintage: {
    name: "📜 Винтаж",
    description: "Сохранение благородной патины старой бумаги",
    filters: { contrast: 10, warmth: 15, whiten: 5, sharpness: 8 },
  },
  text: {
    name: "🔤 Четкий текст",
    description: "Максимальная читаемость страниц и автографов",
    filters: { brightness: -5, contrast: 30, sharpness: 25, whiten: 30 },
  },
  bw: {
    name: "⚪ Черно-белый",
    description: "Обесцвечивание и удаление цветовых шумов",
    filters: { saturation: -100, contrast: 25, sharpness: 15, whiten: 25 },
  },
};

export class StudioEngine {
  private cropper: Cropper | null = null;
  private currentTransform: StudioTransformState;
  private cropRatio: CropRatio = "3:4";
  private onStateChange?: (state: StudioTransformState) => void;

  constructor(
    initialTransform: StudioTransformState = DEFAULT_STUDIO_TRANSFORM,
    onStateChange?: (state: StudioTransformState) => void
  ) {
    this.currentTransform = JSON.parse(JSON.stringify(initialTransform));
    this.onStateChange = onStateChange;
  }

  public init(imgElement: HTMLImageElement): void {
    this.destroy();

    this.cropper = new Cropper(imgElement, {
      aspectRatio: this.cropRatio === "3:4" ? 3 / 4 : NaN,
      viewMode: 1,
      dragMode: "move",
      autoCropArea: 0.95,
      restore: false,
      guides: true,
      center: true,
      highlight: false,
      cropBoxMovable: true,
      cropBoxResizable: true,
      toggleDragModeOnDblclick: false,
      ready: () => {
        if (this.currentTransform.crop && this.cropper) {
          const c = this.currentTransform.crop;
          this.cropper.setData({
            x: c.x,
            y: c.y,
            width: c.width,
            height: c.height,
            rotate: this.currentTransform.rotation,
          });
        }
      },
      cropend: () => {
        this.syncCropBoxFromCropper();
      },
    });
  }

  public destroy(): void {
    if (this.cropper) {
      try {
        this.cropper.destroy();
      } catch (err) {
        console.warn("Cropper destroy error:", err);
      }
      this.cropper = null;
    }
  }

  public setCropRatio(ratio: CropRatio): void {
    this.cropRatio = ratio;
    if (this.cropper) {
      this.cropper.setAspectRatio(ratio === "3:4" ? 3 / 4 : NaN);
    }
  }

  public getCropRatio(): CropRatio {
    return this.cropRatio;
  }

  public setRotation(degrees: number): void {
    this.currentTransform.rotation = Math.round(degrees);
    if (this.cropper) {
      this.cropper.rotateTo(this.currentTransform.rotation);
      this.syncCropBoxFromCropper();
    }
    this.notifyChange();
  }

  public rotateStep(deltaDegrees: number): void {
    const next = (this.currentTransform.rotation + deltaDegrees) % 360;
    this.setRotation(next);
  }

  public setFilter<K extends keyof StudioFilters>(key: K, value: number): void {
    this.currentTransform.filters[key] = value;
    this.notifyChange();
  }

  public applyPreset(presetKey: keyof typeof STUDIO_PRESETS): void {
    const preset = STUDIO_PRESETS[presetKey];
    if (!preset) return;

    this.currentTransform.filters = {
      ...DEFAULT_STUDIO_TRANSFORM.filters,
      ...preset.filters,
    };
    this.notifyChange();
  }

  public setAiWhite(enabled: boolean): void {
    this.currentTransform.useAiWhite = enabled;
    this.notifyChange();
  }

  public applyState(state: StudioTransformState): void {
    this.currentTransform = JSON.parse(JSON.stringify(state));
    if (this.cropper) {
      if (state.crop) {
        this.cropper.setData({
          x: state.crop.x,
          y: state.crop.y,
          width: state.crop.width,
          height: state.crop.height,
          rotate: state.rotation,
        });
      } else {
        this.cropper.rotateTo(state.rotation);
      }
    }
    this.notifyChange();
  }

  public getTransform(): StudioTransformState {
    this.syncCropBoxFromCropper();
    return JSON.parse(JSON.stringify(this.currentTransform));
  }

  public reset(): void {
    this.currentTransform = JSON.parse(JSON.stringify(DEFAULT_STUDIO_TRANSFORM));
    if (this.cropper) {
      this.cropper.reset();
      this.cropper.rotateTo(0);
    }
    this.notifyChange();
  }

  private syncCropBoxFromCropper(): void {
    if (!this.cropper) return;
    const data = this.cropper.getData(true);
    const box: StudioCropBox = {
      x: Math.round(data.x),
      y: Math.round(data.y),
      width: Math.round(data.width),
      height: Math.round(data.height),
    };
    this.currentTransform.crop = box;
    this.currentTransform.rotation = Math.round(data.rotate || 0);
  }

  private notifyChange(): void {
    if (this.onStateChange) {
      this.onStateChange(this.getTransform());
    }
  }
}
