import fs from "node:fs";
import path from "node:path";

// Build-time reader for data/history/*.jsonl → chart-ready series.
// Each point: [isoTs, value]. Sparse/malformed lines are skipped, never fatal.

const HISTORY_DIR = path.join(process.cwd(), "..", "data", "history");

export type SeriesPoint = [string, number];
export type GpuTrendPayload = {
  // gpu class -> series name -> points
  gpus: Record<string, Record<string, SeriesPoint[]>>;
};

function readLines(name: string): Record<string, unknown>[] {
  try {
    const raw = fs.readFileSync(path.join(HISTORY_DIR, name), "utf8");
    return raw
      .split("\n")
      .filter(Boolean)
      .map((l) => {
        try {
          return JSON.parse(l) as Record<string, unknown>;
        } catch {
          return null;
        }
      })
      .filter((x): x is Record<string, unknown> => x !== null);
  } catch {
    return [];
  }
}

// Strip form-factor/memory suffixes ("H100 SXM", "A100 PCIe 80GB") to the base class.
function baseGpu(name: string): string {
  return name
    .replace(/\s+(SXM\d*|NVL|PCIe)(\s+\d+GB)?$/i, "")
    .replace(/\s+\d+GB$/i, "")
    .trim();
}

const CHART_GPUS = ["H100", "H200", "B200", "A100"];

function push(
  out: GpuTrendPayload["gpus"],
  gpu: string,
  series: string,
  ts: string,
  v: unknown
) {
  if (typeof v !== "number" || !isFinite(v) || v <= 0) return;
  if (!CHART_GPUS.includes(gpu)) return;
  ((out[gpu] ??= {})[series] ??= []).push([ts, Math.round(v * 10000) / 10000]);
}

export function loadGpuTrend(): GpuTrendPayload {
  const out: GpuTrendPayload["gpus"] = {};

  for (const line of readLines("neoclouds_backfill.jsonl")) {
    const ts = line.ts as string;
    const mins = (line.min_per_gpu ?? {}) as Record<string, number>;
    for (const [g, v] of Object.entries(mins)) push(out, baseGpu(g), "Spot floor (backfill)", ts, v);
  }

  // External backfill (see data/history/BACKFILL_PROVENANCE.md): on-demand rate
  // cards only — spot/marketplace kinds excluded to keep series semantics uniform.
  const EXT_PROVIDER_NAMES: Record<string, string> = {
    runpod: "RunPod (ext)",
    lambda: "Lambda",
    nebius: "Nebius",
    crusoe: "Crusoe",
    coreweave: "CoreWeave",
    // vast.ai intentionally absent: its rows carry marketplace MIN price
    // (unverified-host junk floors); the median backfill below replaces it
  };
  for (const line of readLines("backfill_external.jsonl")) {
    if (line.kind !== "ondemand") continue;
    const ts = line.ts as string;
    const name = EXT_PROVIDER_NAMES[line.provider as string];
    if (!name) continue;
    const prices = (line.prices ?? {}) as Record<string, number>;
    const byBase: Record<string, number> = {};
    for (const [g, v] of Object.entries(prices)) {
      if (typeof v !== "number" || v <= 0) continue;
      const b = baseGpu(g);
      byBase[b] = Math.min(byBase[b] ?? Infinity, v);
    }
    for (const [g, v] of Object.entries(byBase)) push(out, g, name, ts, v);
  }

  for (const line of readLines("neoclouds.jsonl")) {
    const ts = line.ts as string;
    const prov = (line.providers ?? {}) as Record<string, Record<string, number>>;
    for (const [g, v] of Object.entries(prov.runpod ?? {})) push(out, baseGpu(g), "RunPod", ts, v);
    for (const [g, v] of Object.entries(prov.datacrunch ?? {})) push(out, baseGpu(g), "DataCrunch", ts, v);
  }

  // Vast median backfill: same bundles API + per-GPU normalization as our
  // collector, recorded daily by gpu-pricing-tracker since 2026-05-08. Kept as
  // a separate "(ext)" series because their offer filter differs slightly
  // (~5-10% level offset vs ours on the same day).
  for (const line of readLines("vast_backfill.jsonl")) {
    const ts = line.ts as string;
    const gpus = (line.gpus ?? {}) as Record<string, { median_dph?: number }>;
    for (const [g, v] of Object.entries(gpus)) {
      if (typeof v?.median_dph === "number") push(out, baseGpu(g), "Vast median (ext)", ts, v.median_dph);
    }
  }

  for (const line of readLines("vast.jsonl")) {
    const ts = line.ts as string;
    const gpus = (line.gpus ?? {}) as Record<string, { median_dph?: number }>;
    // one vast series per base class: median of the class's form-factor medians
    const byBase: Record<string, number[]> = {};
    for (const [g, v] of Object.entries(gpus)) {
      if (typeof v?.median_dph === "number") (byBase[baseGpu(g)] ??= []).push(v.median_dph);
    }
    for (const [g, arr] of Object.entries(byBase)) {
      const sorted = [...arr].sort((a, b) => a - b);
      const med = sorted[Math.floor(sorted.length / 2)];
      push(out, g, "Vast median", ts, med);
    }
  }

  for (const line of readLines("hyperscaler.jsonl")) {
    const ts = line.ts as string;
    const azure = (line.azure ?? {}) as Record<
      string,
      { gpu?: string; ondemand_gpu_hr?: number; spot_vm_hr?: number; gpus_per_vm?: number }
    >;
    // cheapest OD + spot per base gpu across SKUs
    const od: Record<string, number> = {};
    const spot: Record<string, number> = {};
    for (const sku of Object.values(azure)) {
      const g = baseGpu(sku.gpu ?? "");
      if (typeof sku.ondemand_gpu_hr === "number")
        od[g] = Math.min(od[g] ?? Infinity, sku.ondemand_gpu_hr);
      if (typeof sku.spot_vm_hr === "number" && sku.gpus_per_vm)
        spot[g] = Math.min(spot[g] ?? Infinity, sku.spot_vm_hr / sku.gpus_per_vm);
    }
    for (const [g, v] of Object.entries(od)) push(out, g, "Azure on-demand", ts, v);
    for (const [g, v] of Object.entries(spot)) push(out, g, "Azure spot", ts, v);
  }

  for (const series of Object.values(out))
    for (const pts of Object.values(series)) pts.sort((a, b) => a[0].localeCompare(b[0]));

  return { gpus: out };
}
