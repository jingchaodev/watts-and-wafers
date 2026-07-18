import fs from "fs";
import path from "path";
import type {
  AllData,
  VastData,
  NeocloudsData,
  HyperscalerData,
  OpenRouterData,
  MemoryData,
  CompositeData,
  SignalsData,
  SignalEventsData,
} from "./types";

// Data lives one level up from web/, per the repo layout:
//   /root/watts-and-wafers/data/latest/*.json
//   /root/watts-and-wafers/data/history/*.jsonl
// Read at BUILD TIME only — never at request time, never from the client.
const DATA_DIR = path.join(process.cwd(), "..", "data");
const LATEST_DIR = path.join(DATA_DIR, "latest");
const HISTORY_DIR = path.join(DATA_DIR, "history");

function readJsonSafe<T>(filePath: string, fallback: T): T {
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") {
      return parsed as T;
    }
    return fallback;
  } catch {
    // Missing file, unreadable, or invalid JSON — degrade gracefully, never throw.
    return fallback;
  }
}

function readJsonlSafe<T>(filePath: string): T[] {
  try {
    const raw = fs.readFileSync(filePath, "utf-8");
    const lines = raw.split("\n").filter((l) => l.trim().length > 0);
    const out: T[] = [];
    for (const line of lines) {
      try {
        out.push(JSON.parse(line) as T);
      } catch {
        // Skip malformed lines rather than failing the whole series.
      }
    }
    return out;
  } catch {
    return [];
  }
}

export function loadAllData(): AllData {
  const vast = readJsonSafe<VastData>(path.join(LATEST_DIR, "vast.json"), {});
  const neoclouds = readJsonSafe<NeocloudsData>(
    path.join(LATEST_DIR, "neoclouds.json"),
    {}
  );
  const hyperscaler = readJsonSafe<HyperscalerData>(
    path.join(LATEST_DIR, "hyperscaler.json"),
    {}
  );
  const openrouter = readJsonSafe<OpenRouterData>(
    path.join(LATEST_DIR, "openrouter.json"),
    {}
  );
  const memory = readJsonSafe<MemoryData>(
    path.join(LATEST_DIR, "memory.json"),
    {}
  );
  const composite = readJsonSafe<CompositeData>(
    path.join(LATEST_DIR, "composite.json"),
    {}
  );
  const signals = readJsonSafe<SignalsData>(
    path.join(LATEST_DIR, "signals.json"),
    {}
  );

  const history = {
    vast: readJsonlSafe<AllData["history"]["vast"][number]>(
      path.join(HISTORY_DIR, "vast.jsonl")
    ),
    composite: readJsonlSafe<AllData["history"]["composite"][number]>(
      path.join(HISTORY_DIR, "composite.jsonl")
    ),
    openrouter: readJsonlSafe<AllData["history"]["openrouter"][number]>(
      path.join(HISTORY_DIR, "openrouter.jsonl")
    ),
    memory: readJsonlSafe<AllData["history"]["memory"][number]>(
      path.join(HISTORY_DIR, "memory.jsonl")
    ),
    neoclouds: readJsonlSafe<AllData["history"]["neoclouds"][number]>(
      path.join(HISTORY_DIR, "neoclouds.jsonl")
    ),
  };

  return { vast, neoclouds, hyperscaler, openrouter, memory, composite, signals, history };
}

/** signal_events.json lives alongside the other latest/*.json files but isn't
 * part of AllData (it's consumed by a single feed section) — load separately. */
export function loadSignalEvents(): SignalEventsData {
  return readJsonSafe<SignalEventsData>(
    path.join(LATEST_DIR, "signal_events.json"),
    {}
  );
}

/** Max asof across all latest/*.json files, for the header timestamp. */
export function maxAsof(data: AllData): string | null {
  const candidates = [
    data.vast.asof,
    data.neoclouds.asof,
    data.hyperscaler.asof,
    data.openrouter.asof,
    data.memory.asof,
    data.composite.asof,
  ].filter((x): x is string => Boolean(x));
  if (candidates.length === 0) return null;
  return candidates.reduce((max, cur) => (cur > max ? cur : max));
}

/** Is this asof considered stale relative to `hours` freshness budget? */
export function isStale(asof: string | undefined | null, hours: number): boolean {
  if (!asof) return true;
  const t = Date.parse(asof);
  if (Number.isNaN(t)) return true;
  const ageMs = Date.now() - t;
  return ageMs > hours * 60 * 60 * 1000;
}

export type FreshnessTier = "green" | "amber" | "red";

/** 3-tier freshness: green < hours, amber hours..2x, red beyond 2x. Missing/
 * unparsable asof is always red (worst case, matches isStale's fail-safe). */
export function freshnessTier(asof: string | undefined | null, hours: number): FreshnessTier {
  if (!asof) return "red";
  const t = Date.parse(asof);
  if (Number.isNaN(t)) return "red";
  const ageHours = (Date.now() - t) / (60 * 60 * 1000);
  if (ageHours < hours) return "green";
  if (ageHours < hours * 2) return "amber";
  return "red";
}

export function formatAsof(asof: string | undefined | null): string {
  if (!asof) return "unknown";
  const t = Date.parse(asof);
  if (Number.isNaN(t)) return asof;
  const d = new Date(t);
  return d.toISOString().replace("T", " ").replace(/\.\d+Z$/, " UTC");
}
