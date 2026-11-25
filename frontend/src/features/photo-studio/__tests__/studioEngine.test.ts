import { describe, it, expect, vi } from "vitest";
import { StudioEngine, STUDIO_PRESETS } from "../StudioEngine";
import { DEFAULT_STUDIO_TRANSFORM } from "../HistoryStack";

// Mock Cropper constructor
vi.mock("cropperjs", () => {
  return {
    default: vi.fn().mockImplementation(() => ({
      setData: vi.fn(),
      getData: vi.fn().mockReturnValue({ x: 10, y: 10, width: 300, height: 400, rotate: 0 }),
      setAspectRatio: vi.fn(),
      rotateTo: vi.fn(),
      reset: vi.fn(),
      destroy: vi.fn(),
    })),
  };
});

describe("StudioEngine (ADR-10 Isolated Cropper & Adjustment Pipeline)", () => {
  it("defines standard 4 book photo presets", () => {
    expect(STUDIO_PRESETS.auto).toBeDefined();
    expect(STUDIO_PRESETS.vintage).toBeDefined();
    expect(STUDIO_PRESETS.text).toBeDefined();
    expect(STUDIO_PRESETS.bw).toBeDefined();

    expect(STUDIO_PRESETS.bw.filters.saturation).toBe(-100);
    expect(STUDIO_PRESETS.text.filters.contrast).toBe(30);
  });

  it("applies filters and notifies callback", () => {
    const notifySpy = vi.fn();
    const engine = new StudioEngine(DEFAULT_STUDIO_TRANSFORM, notifySpy);

    engine.setFilter("brightness", 20);
    expect(engine.getTransform().filters.brightness).toBe(20);
    expect(notifySpy).toHaveBeenCalled();

    engine.setFilter("whiten", 35);
    expect(engine.getTransform().filters.whiten).toBe(35);
  });

  it("applies preset cleanly", () => {
    const engine = new StudioEngine();
    engine.applyPreset("bw");

    const t = engine.getTransform();
    expect(t.filters.saturation).toBe(-100);
    expect(t.filters.contrast).toBe(25);
  });

  it("toggles AI White Background", () => {
    const engine = new StudioEngine();
    expect(engine.getTransform().useAiWhite).toBe(false);

    engine.setAiWhite(true);
    expect(engine.getTransform().useAiWhite).toBe(true);
  });

  it("handles rotation steps", () => {
    const engine = new StudioEngine();
    expect(engine.getTransform().rotation).toBe(0);

    engine.rotateStep(90);
    expect(engine.getTransform().rotation).toBe(90);

    engine.rotateStep(90);
    expect(engine.getTransform().rotation).toBe(180);

    engine.rotateStep(-90);
    expect(engine.getTransform().rotation).toBe(90);
  });

  it("changes crop ratio", () => {
    const engine = new StudioEngine();
    expect(engine.getCropRatio()).toBe("3:4");

    engine.setCropRatio("free");
    expect(engine.getCropRatio()).toBe("free");
  });
});

