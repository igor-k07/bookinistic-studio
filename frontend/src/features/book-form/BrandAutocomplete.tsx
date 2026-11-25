import React, { useEffect, useRef, useState } from "react";

interface Props {
  value: string;
  onChange: (val: string) => void;
  options: string[];
  placeholder?: string;
  error?: string;
}

export function BrandAutocomplete({
  value,
  onChange,
  options,
  placeholder = "Выберите или введите...",
  error,
}: Props): React.JSX.Element {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState(value);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setQuery(value);
  }, [value]);

  // Click outside listener
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const filtered = options
    .filter((o) => o.toLowerCase().includes((query || "").toLowerCase()))
    .slice(0, 50);

  const handleSelect = (item: string) => {
    setQuery(item);
    onChange(item);
    setIsOpen(false);
  };

  return (
    <div ref={containerRef} className="relative w-full">
      <input
        type="text"
        value={query}
        placeholder={placeholder}
        onFocus={() => setIsOpen(true)}
        onChange={(e) => {
          setQuery(e.target.value);
          onChange(e.target.value);
          setIsOpen(true);
        }}
        className={`w-full rounded-lg border bg-slate-800 px-3 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-2 ${
          error
            ? "border-rose-500 focus:ring-rose-500/50"
            : "border-slate-700 focus:border-emerald-500 focus:ring-emerald-500/30"
        }`}
      />
      {error && <span className="mt-1 block text-xs text-rose-400">{error}</span>}

      {isOpen && filtered.length > 0 && (
        <div className="absolute z-40 mt-1 max-h-56 w-full overflow-y-auto rounded-lg border border-slate-700 bg-slate-800/95 py-1 shadow-2xl backdrop-blur-md scrollbar-thin">
          {filtered.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => handleSelect(item)}
              className="w-full px-3 py-1.5 text-left text-xs text-slate-200 hover:bg-emerald-600 hover:text-white"
            >
              {item}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
