/**
 * Diff-based History Stack for Photo Studio Undo / Redo.
 *
 * Conforms to Architectural Guardrail 10:
 * Stores lightweight JSON parameter diffs (~200 bytes), never image blobs or base64.
 */

export interface StudioFilters {
  brightness: number;
  contrast: number;
  saturation: number;
  sharpness: number;
  highlights: number;
  shadows: number;
  whiten: number;
  warmth: number;
}

export interface StudioCropBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface StudioTransformState {
  crop: StudioCropBox | null;
  rotation: number;
  useAiWhite: boolean;
  filters: StudioFilters;
}

export const DEFAULT_STUDIO_TRANSFORM: StudioTransformState = {
  crop: null,
  rotation: 0,
  useAiWhite: false,
  filters: {
    brightness: 0,
    contrast: 0,
    saturation: 0,
    sharpness: 0,
    highlights: 0,
    shadows: 0,
    whiten: 0,
    warmth: 0,
  },
};

export class HistoryStack {
  private past: StudioTransformState[] = [];
  private present: StudioTransformState;
  private future: StudioTransformState[] = [];
  private readonly maxDepth: number;

  constructor(initialState: StudioTransformState = DEFAULT_STUDIO_TRANSFORM, maxDepth = 50) {
    this.present = JSON.parse(JSON.stringify(initialState));
    this.maxDepth = maxDepth;
  }

  public getCurrentState(): StudioTransformState {
    return JSON.parse(JSON.stringify(this.present));
  }

  public push(newState: StudioTransformState): void {
    const serializedNew = JSON.stringify(newState);
    const serializedCurrent = JSON.stringify(this.present);
    if (serializedNew === serializedCurrent) {
      return; // No-op if state did not change
    }

    this.past.push(this.present);
    if (this.past.length > this.maxDepth) {
      this.past.shift();
    }
    this.present = JSON.parse(serializedNew);
    this.future = []; // Clear redo stack on new action
  }

  public canUndo(): boolean {
    return this.past.length > 0;
  }

  public canRedo(): boolean {
    return this.future.length > 0;
  }

  public undo(): StudioTransformState | null {
    if (!this.canUndo()) return null;
    const previous = this.past.pop();
    if (!previous) return null;

    this.future.unshift(this.present);
    this.present = previous;
    return this.getCurrentState();
  }

  public redo(): StudioTransformState | null {
    if (!this.canRedo()) return null;
    const next = this.future.shift();
    if (!next) return null;

    this.past.push(this.present);
    this.present = next;
    return this.getCurrentState();
  }

  public clear(resetState: StudioTransformState = DEFAULT_STUDIO_TRANSFORM): void {
    this.past = [];
    this.future = [];
    this.present = JSON.parse(JSON.stringify(resetState));
  }
}

