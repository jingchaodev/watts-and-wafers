// Types matching docs/DATA_CONTRACT.md. All fields are optional/nullable at the
// TypeScript level even where the contract implies "always present" — collectors can
// degrade gracefully and the site must never crash the build on missing data.

export interface VastGpuStat {
  offers?: number;
  total_gpus?: number;
  median_dph?: number;
  p25_dph?: number;
  min_dph?: number;
}

export interface VastData {
  asof?: string;
  gpus?: Record<string, VastGpuStat>;
  errors?: string[];
}

export interface NeocloudsData {
  asof?: string;
  providers?: Record<string, Record<string, number>>;
  errors?: string[];
}

export interface AzureSku {
  gpu?: string;
  gpus_per_vm?: number;
  ondemand_vm_hr?: number;
  spot_vm_hr?: number | null;
  ondemand_gpu_hr?: number;
  region?: string;
}

export interface HyperscalerData {
  asof?: string;
  azure?: Record<string, AzureSku>;
  errors?: string[];
}

export interface OpenRouterModel {
  id?: string;
  name?: string;
  prompt_usd_per_m?: number;
  completion_usd_per_m?: number;
  context?: number;
}

export interface TokensDaily {
  date?: string;
  total_b_tokens?: number;
  top_models?: { slug?: string; b_tokens?: number }[];
}

export interface OpenRouterData {
  asof?: string;
  n_models?: number;
  models?: OpenRouterModel[];
  frontier_median_completion_usd_per_m?: number;
  tokens_daily?: TokensDaily | null;
  errors?: string[];
}

export interface DramSpotItem {
  item?: string;
  avg?: number;
  chg_pct?: number;
}

export interface NandNote {
  date?: string;
  summary?: string;
  url?: string;
}

export interface ProxyStock {
  price?: number;
  chg_pct?: number;
}

export interface MemoryData {
  asof?: string;
  dram_spot?: DramSpotItem[];
  nand_note?: NandNote;
  proxies?: Record<string, ProxyStock>;
  errors?: string[];
}

export type Direction = "up" | "down" | "flat";

export interface CompositeSignal {
  key?: string;
  weight?: number;
  z?: number;
  direction?: Direction;
  detail?: string;
}

export interface CompositeData {
  asof?: string;
  index?: number;
  label?: string;
  signals?: CompositeSignal[];
}

// ---- History (jsonl) shapes ----

export interface VastHistoryLine {
  ts?: string;
  gpus?: Record<string, { offers?: number; median_dph?: number }>;
}

export interface CompositeHistoryLine {
  ts?: string;
  index?: number;
}

export interface OpenRouterHistoryLine {
  ts?: string;
  frontier_median_completion_usd_per_m?: number;
  n_models?: number;
}

export interface MemoryHistoryLine {
  ts?: string;
  dram_spot_avg_chg_pct?: number;
  ddr5_avg?: number;
}

export interface NeocloudsHistoryLine {
  ts?: string;
  providers?: Record<string, Record<string, number>>;
}

export interface AllData {
  vast: VastData;
  neoclouds: NeocloudsData;
  hyperscaler: HyperscalerData;
  openrouter: OpenRouterData;
  memory: MemoryData;
  composite: CompositeData;
  history: {
    vast: VastHistoryLine[];
    composite: CompositeHistoryLine[];
    openrouter: OpenRouterHistoryLine[];
    memory: MemoryHistoryLine[];
    neoclouds: NeocloudsHistoryLine[];
  };
}
