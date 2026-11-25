import { describe, it, expect } from "vitest";
import {
  SOVIET_FORMAT_TABLE,
  PAPER_DENSITY_MAP,
  calculateGostDimensionsAndWeight,
} from "../GostPhysicsCalc";

describe("GOST Physics Calculator (ADR-5 SSOT)", () => {
  it("defines standard Soviet book formats", () => {
    expect(SOVIET_FORMAT_TABLE["84×108/32"]).toEqual({
      name: "84×108/32 (Стандартный)",
      width: 130,
      length: 200,
    });
    expect(SOVIET_FORMAT_TABLE["70×108/16"]).toBeDefined();
    expect(SOVIET_FORMAT_TABLE["60×90/16"]).toBeDefined();
    expect(PAPER_DENSITY_MAP["Офсетная"]).toBe(80);
    expect(PAPER_DENSITY_MAP["Газетная"]).toBe(50);
  });

  it("calculates dimensions and weight for standard hardcover book", () => {
    // 84x108/32 format, 320 pages, hardcover, offset paper
    const res = calculateGostDimensionsAndWeight(
      "84×108/32",
      320,
      "Твердый переплет",
      "Офсетная"
    );

    expect(res.width).toBe(130);
    expect(res.length).toBe(200);
    // height = round((320 / 2) * 0.09 + 4) = round(160 * 0.09 + 4) = round(14.4 + 4) = 18 mm
    expect(res.height).toBe(18);
    // weight > 200g
    expect(res.weight).toBeGreaterThan(200);
    expect(res.weight).toBeLessThan(600);
  });

  it("calculates lower thickness and weight for softcover newsprint", () => {
    const res = calculateGostDimensionsAndWeight(
      "84×108/32",
      320,
      "Мягкая обложка",
      "Газетная"
    );

    expect(res.width).toBe(130);
    expect(res.length).toBe(200);
    // softcover: 0.075 mm per leaf + 1 mm cover = 160 * 0.075 + 1 = 12 + 1 = 13 mm
    expect(res.height).toBe(13);
    // Gasette paper density is 50 vs 80 for offset
    expect(res.weight).toBeLessThan(350);
  });

  it("handles fallback format gracefully", () => {
    const res = calculateGostDimensionsAndWeight(
      "UNKNOWN_FORMAT",
      100,
      "Твердый переплет",
      "Типографская"
    );
    expect(res.width).toBe(130);
    expect(res.length).toBe(200);
    expect(res.height).toBeGreaterThanOrEqual(5);
    expect(res.weight).toBeGreaterThanOrEqual(50);
  });
});
