# Watts & Wafers — Data Contract

The seam between collectors (Python, VPS cron) and the web app (Next.js, Vercel).
Collectors write JSON here; the site reads it at build time. Neither side imports the other.

## Files

### `data/latest/vast.json` (hourly) — THE availability signal
```json
{
  "asof": "2026-07-17T20:00:00Z",
  "gpus": {
    "H100 SXM": {"offers": 132, "total_gpus": 611, "median_dph": 1.87, "p25_dph": 1.55, "min_dph": 1.10},
    "H200": {"offers": 41, "total_gpus": 210, "median_dph": 2.35, "p25_dph": 2.05, "min_dph": 1.80},
    "B200": {"offers": 7, "total_gpus": 42, "median_dph": 4.10, "p25_dph": 3.90, "min_dph": 3.60},
    "RTX 4090": {"offers": 900, "total_gpus": 2100, "median_dph": 0.35, "p25_dph": 0.28, "min_dph": 0.18}
  },
  "errors": []
}
```
`offers` = count of rentable offers returned for that GPU class. The time series of `offers`
is the sold-out proxy: falling offers + rising median = demand tightening.

### `data/latest/neoclouds.json` (hourly)
Ported RunPod + DataCrunch logic from the wiki gpu_snapshot.
```json
{
  "asof": "...",
  "providers": {
    "runpod":     {"H100": 2.19, "H200": 2.59, "B200": 5.98},
    "datacrunch": {"H100": 2.20, "H200": 2.65}
  },
  "errors": []
}
```
Key = normalized GPU name (H100 / H200 / B200 / GB200 / A100 / L40S / RTX 4090 / MI300X);
value = lowest on-demand $/GPU-hr.

### `data/latest/hyperscaler.json` (daily)
Azure Retail Prices API, ND-series GPU SKUs.
```json
{
  "asof": "...",
  "azure": {
    "ND96isr_H100_v5": {"gpu": "H100", "gpus_per_vm": 8, "ondemand_vm_hr": 55.84, "spot_vm_hr": 22.1, "ondemand_gpu_hr": 6.98, "region": "eastus"},
    "ND96isr_H200_v5": {"gpu": "H200", "gpus_per_vm": 8, "ondemand_vm_hr": 63.0, "spot_vm_hr": null, "ondemand_gpu_hr": 7.88, "region": "eastus"}
  },
  "errors": []
}
```

### `data/latest/openrouter.json` (daily)
```json
{
  "asof": "...",
  "n_models": 480,
  "models": [
    {"id": "openai/gpt-5.6", "name": "GPT-5.6", "prompt_usd_per_m": 3.5, "completion_usd_per_m": 14.0, "context": 400000}
  ],
  "frontier_median_completion_usd_per_m": 11.0,
  "tokens_daily": null,
  "errors": []
}
```
`models` sorted by completion price desc, capped at 150 entries. `tokens_daily` stays null
until the OpenRouter API key lands; then it becomes
`{"date": "...", "total_b_tokens": 123.4, "top_models": [{"slug": "...", "b_tokens": 9.8}]}`.

### `data/latest/memory.json` (daily)
```json
{
  "asof": "...",
  "dram_spot": [
    {"item": "DDR5 16G (2Gx8) 4800/5600", "avg": 6.83, "chg_pct": 1.2}
  ],
  "nand_note": {"date": "2026-07-15", "summary": "NAND wafer spot +2.1% WoW", "url": "..."},
  "proxies": {"MU": {"price": 0.0, "chg_pct": 0.0}, "000660.KS": {"price": 0.0, "chg_pct": 0.0}},
  "errors": []
}
```

### `data/latest/composite.json` (after every collector run)
```json
{
  "asof": "...",
  "index": 62.5,
  "label": "TIGHTENING",
  "signals": [
    {"key": "gpu_availability", "weight": 0.35, "z": 1.2, "direction": "up", "detail": "Vast H100 offers -18% (7d)"},
    {"key": "token_economics",  "weight": 0.25, "z": 0.4, "direction": "up", "detail": "frontier $/M -3% (30d)"},
    {"key": "memory",           "weight": 0.25, "z": 0.8, "direction": "up", "detail": "DDR5 spot +4.1% (7d)"},
    {"key": "gpu_price",        "weight": 0.15, "z": 0.2, "direction": "flat", "detail": "neocloud H100 median flat"}
  ]
}
```
`index` = 50 + 12.5 × Σ(weight·z), clamped 0–100. Labels: ≥65 SURGING, ≥55 TIGHTENING,
45–55 NEUTRAL, ≥35 SOFTENING, <35 GLUT. z-scores computed from `data/history/*.jsonl`
trailing windows (availability 7d vs prior 30d; prices 30d).

### `data/latest/crosscheck.json` (daily, after vast/neoclouds/hyperscaler)
```json
{
  "asof": "...",
  "flags": [
    {"gpu": "H100", "provider": "runpod", "price": 0.42, "cohort_median": 2.10, "ratio": 0.2}
  ],
  "errors": []
}
```
For each GPU class, compares every provider's latest on-demand $/GPU-hr (vast's median_dph,
each neocloud provider, azure's ondemand_gpu_hr) to the cohort median across providers; flags
any provider whose |log-deviation| > ln(2.5) (i.e. price is >2.5x off the cohort median, either
direction). Informational only — does not gate/exclude anything; the site may render it later.
Requires >=2 providers reporting a class before a deviation is meaningful.

### `data/history/quarantine.jsonl` (append-only, validation layer)
```json
{"ts": "...", "source": "vast", "item": {"gpu_name": "H100 SXM", "median_dph": 45.0}, "reason": "H100 SXM: $45.0000/gpu-hr above plausibility ceiling $16 (canon=H100)"}
```
Every value/record excluded from a `latest/*.json` file by `collectors/validation.py`'s price
or relation checks is appended here — nothing fails silently. See `validation.py` for the
per-GPU-class plausibility bands (deliberately wide: they catch unit errors, not market moves).

## History

Every run appends one compact line per file to `data/history/<name>.jsonl`:
```json
{"ts": "2026-07-17T20:00:00Z", "gpus": {"H100 SXM": {"offers": 132, "median_dph": 1.87}, "...": {}}}
```
History lines keep only the fields needed for sparklines/z-scores (offers, median/lowest
prices, spot avg+chg, frontier price median, index). Rotation: when a history file exceeds
20,000 lines, drop the oldest 25% (collectors handle this).

## Conventions

- All writes atomic: tmp file + `os.replace`.
- A failing source NEVER breaks the file: record in `errors[]`, keep last-known-good values
  absent (site renders "stale" from `asof`).
- Timestamps UTC ISO-8601 with Z suffix.
- Collectors are stdlib-only Python 3.10+ (urllib, json, re). No pip deps in collectors.
- Env keys (optional, VPS only, never committed): `OPENROUTER_API_KEY`, `LAMBDA_API_KEY`,
  `FINNHUB_KEY` (memory proxies). Absence = graceful degradation.
