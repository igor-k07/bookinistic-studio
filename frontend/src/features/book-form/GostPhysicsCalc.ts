/**
 * GOST Physics Calculator for Desktop UI (SSOT matching ADR-5 and backend domain rules).
 */

export interface SovietFormat {
  name: string;
  width: number;
  length: number;
}

export const SOVIET_FORMAT_TABLE: Record<string, SovietFormat> = {
  "84×108/32": { name: "84×108/32 (Стандартный)", width: 130, length: 200 },
  "70×100/32": { name: "70×100/32 (Увеличенный малый)", width: 120, length: 165 },
  "70×90/32": { name: "70×90/32 (Малый)", width: 107, length: 165 },
  "60×90/16": { name: "60×90/16 (Энциклопедический)", width: 145, length: 215 },
  "70×108/16": { name: "70×108/16 (Увеличенный)", width: 170, length: 260 },
  "84×108/16": { name: "84×108/16 (Большой)", width: 205, length: 260 },
  "60×84/16": { name: "60×84/16 (Популярный)", width: 145, length: 200 },
  "70×90/16": { name: "70×90/16 (Увеличенный средний)", width: 170, length: 215 },
  "60×90/32": { name: "60×90/32 (Карманный)", width: 107, length: 140 },
  "75×90/32": { name: "75×90/32 (Уменьшенный)", width: 110, length: 175 },
  "84×100/32": { name: "84×100/32 (Особый)", width: 125, length: 200 },
  "1/8": { name: "1/8 (Альбомный)", width: 220, length: 290 },
};

export const PAPER_DENSITY_MAP: Record<string, number> = {
  "Типографская": 65,
  "Офсетная": 80,
  "Мелованная": 115,
  "Газетная": 50,
};

export function calculateGostDimensionsAndWeight(
  formatCode: string,
  pages: number,
  coverType: string,
  paperType: string
): { width: number; length: number; height: number; weight: number } {
  const fmt = SOVIET_FORMAT_TABLE[formatCode] || { width: 130, length: 200 };
  const safePages = Math.max(1, pages || 1);
  const isHardcover = coverType.toLowerCase().includes("тверд");

  // Thickness formula
  const pageThicknessMm = isHardcover ? 0.09 : 0.075;
  const coverAllowanceMm = isHardcover ? 4 : 1;
  const rawHeight = Math.round((safePages / 2) * pageThicknessMm + coverAllowanceMm);
  const height = Math.max(5, Math.min(rawHeight, 150));

  // Weight formula
  const density = PAPER_DENSITY_MAP[paperType] || 65;
  const areaM2 = (fmt.width / 1000) * (fmt.length / 1000);
  const leafCount = safePages / 2;
  const blockWeightG = leafCount * areaM2 * density;
  const coverWeightG = isHardcover ? 80 : 20;
  const weight = Math.max(50, Math.round(blockWeightG + coverWeightG));

  return {
    width: fmt.width,
    length: fmt.length,
    height,
    weight,
  };
}
