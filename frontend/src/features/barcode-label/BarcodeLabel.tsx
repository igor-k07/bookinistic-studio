import React from "react";

interface Props {
  article: string;
  barcode: string;
  title: string;
  author: string;
  price: number;
  storageLocation: string;
}

/**
 * Pure SVG EAN-13 barcode generator (Zero external dependencies).
 */
const EAN13_L_CODES = [
  "0001101", "0011001", "0010011", "0111101", "0100011",
  "0110001", "0101111", "0111011", "0110111", "0001011",
];
const EAN13_G_CODES = [
  "0100111", "0110011", "0011011", "0100001", "0011101",
  "0111001", "0000101", "0010001", "0001001", "0010111",
];
const EAN13_R_CODES = [
  "1110010", "1100110", "1101100", "1000010", "1011100",
  "1001110", "1010000", "1000100", "1001000", "1110100",
];
const FIRST_DIGIT_PARITY = [
  "LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
  "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL",
];

function generateEan13SvgPattern(code: string): string {
  const digits = code.replace(/\D/g, "");
  if (digits.length < 12) {
    return "";
  }
  const full = digits.slice(0, 13).padEnd(13, "0");
  const first = parseInt(full[0], 10);
  const parity = FIRST_DIGIT_PARITY[first] || "LLLLLL";

  let pattern = "101"; // start guard
  // Left 6 digits
  for (let i = 1; i <= 6; i++) {
    const d = parseInt(full[i], 10);
    const p = parity[i - 1];
    pattern += p === "L" ? EAN13_L_CODES[d] : EAN13_G_CODES[d];
  }
  pattern += "01010"; // center guard
  // Right 6 digits
  for (let i = 7; i <= 12; i++) {
    const d = parseInt(full[i], 10);
    pattern += EAN13_R_CODES[d];
  }
  pattern += "101"; // end guard
  return pattern;
}

export function BarcodeLabel({
  article,
  barcode,
  title,
  author,
  price,
  storageLocation,
}: Props): React.JSX.Element {
  const pattern = generateEan13SvgPattern(barcode);

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className="flex flex-col items-center gap-3 rounded-2xl border border-slate-800 bg-slate-900/40 p-4 backdrop-blur-md">
      <div className="flex w-full items-center justify-between">
        <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
          Термоэтикетка (58×40 мм)
        </h4>
        <button
          onClick={handlePrint}
          className="rounded-lg bg-slate-800 px-3 py-1 text-xs font-semibold text-emerald-400 hover:bg-slate-700 active:scale-95"
        >
          🖨️ Печать
        </button>
      </div>

      {/* Label Canvas (scaled 58x40 mm) */}
      <div
        id="thermal-label-print"
        className="flex h-[151px] w-[219px] flex-col justify-between rounded-lg bg-white p-2.5 text-black shadow-lg"
      >
        <div className="flex items-start justify-between border-b border-black/10 pb-1">
          <div className="max-w-[130px]">
            <p className="truncate text-[10px] font-bold leading-tight">{title || "Без названия"}</p>
            <p className="truncate text-[9px] text-gray-700 leading-tight">{author || "не указан"}</p>
          </div>
          <div className="text-right">
            <span className="block text-xs font-black">{price > 0 ? `${Math.round(price)} ₽` : "—"}</span>
            {storageLocation && (
              <span className="mt-0.5 inline-block rounded bg-black px-1 text-[8px] font-extrabold text-white">
                {storageLocation}
              </span>
            )}
          </div>
        </div>

        {/* Barcode SVG */}
        <div className="flex flex-col items-center justify-center my-0.5">
          {pattern ? (
            <svg viewBox={`0 0 ${pattern.length} 40`} className="h-8 w-44">
              {pattern.split("").map((bit, idx) =>
                bit === "1" ? (
                  <rect key={idx} x={idx} y="0" width="1" height="40" fill="black" />
                ) : null
              )}
            </svg>
          ) : (
            <div className="flex h-8 w-44 items-center justify-center border border-dashed border-gray-400 text-[9px] text-gray-500">
              Штрихкод отсутствует
            </div>
          )}
          <span className="font-mono text-[9px] font-semibold tracking-widest">
            {barcode || article}
          </span>
        </div>

        <div className="flex items-center justify-between text-[8px] text-gray-600 border-t border-black/10 pt-0.5">
          <span>Арт: {article}</span>
          <span>Bookinistic 2.0</span>
        </div>
      </div>
    </div>
  );
}
