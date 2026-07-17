export function fmtUsd(v: number | undefined | null, decimals = 2): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  return `$${v.toFixed(decimals)}`;
}

export function fmtNum(v: number | undefined | null, decimals = 0): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  return v.toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function fmtPct(v: number | undefined | null, decimals = 1): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(decimals)}%`;
}

export function fmtContext(v: number | undefined | null): string {
  if (v === undefined || v === null || Number.isNaN(v)) return "—";
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(v % 1_000_000 === 0 ? 0 : 1)}M`;
  if (v >= 1_000) return `${Math.round(v / 1000)}K`;
  return String(v);
}

export function directionArrow(direction: string | undefined | null): string {
  if (direction === "up") return "↑";
  if (direction === "down") return "↓";
  return "→";
}

/** Tone convention: rising = clay/strong (demand up), falling = rust, flat = muted. */
export function toneForChange(v: number | undefined | null): "clay" | "rust" | "muted" {
  if (v === undefined || v === null || Number.isNaN(v) || v === 0) return "muted";
  return v > 0 ? "clay" : "rust";
}
