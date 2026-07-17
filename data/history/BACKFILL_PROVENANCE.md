# External Backfill Provenance

Companion to `data/history/backfill_external.jsonl`. Generated 2026-07-17 per the
hunt order in the backfill mission (GitHub git-scraping repos → Wayback Machine).
**No signups/API keys used. No fabricated or interpolated points — gaps stay gaps.**
This file and the JSONL are additive only; no existing repo file was modified.

## Sources included in backfill_external.jsonl

### 1. `github:cherielilili/gpu-pricing-tracker`
- **What it is**: a public, unauthenticated GitHub repo
  (https://github.com/cherielilili/gpu-pricing-tracker) that runs a daily cron
  (`runner.sh` → `scripts/fetch.py`) hitting vast.ai's public bundles API, RunPod's
  pricing page, Lambda/Crusoe/Nebius/SFCompute/CoreWeave pages, and commits
  `data/observations.csv` once per day. Verified via the commit history: 74+
  commits, one per calendar day, each titled `daily snapshot YYYY-MM-DD`,
  git-authored on that date.
- **License/terms**: no LICENSE file in the repo. Treated as public factual
  price-observation data (numbers + timestamps), not creative content; used
  read-only via `raw.githubusercontent.com`, no repo cloned/forked, no code reused.
- **Date range recovered**: **2026-05-08 → 2026-07-17** only (71 distinct dates).
- **Row count included**: 565 lines (provider × date × rental_type granularity),
  covering providers `runpod`, `lambda`, `crusoe`, `nebius`, `sfcompute`,
  `coreweave` (1 day only — dropped from their fetcher after 2026-05-08), and
  `vast.ai`.
- **IMPORTANT — excluded portion**: the repo's CSV also contains rows for
  **2026-02-11 → 2026-05-07** (a second commit, `bb4540c2`, titled "backfill: 86
  days from old gpu-tracker Supabase", claiming migration from a prior database).
  This mission's own verification found that portion **not credible** and it was
  **deliberately excluded**:
  - The repo's very first commit (`10ca11b5`, 2026-05-08) contains only a single
    day of data (2026-05-08, 345 rows) — the repo did not exist before that date.
  - Spot-checking `runpod` `H100_PCIE` on-demand price in the claimed Feb–Apr 2026
    window shows the **exact same value (1.99) and exact same n_offers (2) for
    45+ consecutive days**, sourced from `getdeploying.com` — a live/current-state
    aggregator with no historical API. A real daily scrape of a live aggregator
    would show at least minor jitter in offer counts; a frozen value for 45+ days
    is the signature of a single current snapshot replicated backward to fake a
    time series, not real daily collection.
  - Because "fabrication is forbidden" is a hard constraint here, the entire
    pre-2026-05-08 portion of this repo was **not used**, despite covering a
    valuable gap (Feb–May 2026). Only the day-granular, git-commit-verified,
    internally-volatile (vast.ai) / plausibly-sticky-but-stepwise (runpod,
    lambda rate cards) portion from 2026-05-08 onward was kept.

### 2. `wayback:runpod.io/pricing`
- **What it is**: Wayback Machine (archive.org) snapshots of runpod.io/pricing,
  fetched via the CDX API + direct `web.archive.org/web/<ts>/<url>` retrieval,
  parsed from the page's embedded Next.js/GraphQL JSON cache
  (`securePrice` = on-demand "Secure Cloud", `communityPrice` = on-demand
  "Community Cloud" marketplace rate; both are RunPod's own published rates, not
  spot/bid prices).
- **License/terms**: Internet Archive Wayback Machine is a public, free service;
  archived pages are RunPod's own factual published pricing, fetched read-only,
  no scraping of archive.org beyond the documented CDX/playback APIs, ≤1
  request/~3-5s (some retries needed after transient rate limiting).
- **Date range recovered**: 2025-01-05 → 2025-06-09 (7 usable snapshots).
- **Row count included**: 14 lines (7 dates × 2 kinds: `ondemand` = Secure Cloud,
  `marketplace` = Community Cloud, when available).
- **Parsing note**: only the `securePrice`/`communityPrice` fields are trusted,
  and only when their sibling `secureCloud`/`communityCloud` boolean is `true`.
  RunPod's frontend payload leaves a **stale placeholder** `communityPrice`
  number even when `communityCloud:false` (no community capacity for that GPU
  yet) — e.g. the 2025-01-05 through 2025-03-06 snapshots show
  `"communityPrice":0.5,"communityCloud":false` for H200, which is not a real
  price and was correctly dropped by the parser (H200 first got real community
  pricing, $3.59, in the 2025-04-17 snapshot).

## Sources investigated but NOT usable (explicitly reporting the miss, not padding)

- **GitHub — other repo candidates**: `JarvisLee511/multi-cloud-ai-infrastructure-analysis`
  (no committed historical CSV/JSONL data files surfaced in search, description
  references SEC filings not GPU rental spot data), `SpoodermanCodes/duncan`,
  `Alir3zag/gpu_price_tracker` (Newegg retail GPU hardware prices, not cloud
  rental $/hr — wrong domain), `djg02/GPUTrackerMX` (Mexican retail market, same
  issue). None matched the cloud-rental-$/hr-with-committed-history criterion as
  well as `cherielilili/gpu-pricing-tracker`, so effort was concentrated there
  per the "prioritize depth on the richest source" instruction.
- **Wayback — `datacrunch.io/pricing`**: **zero snapshots** in the CDX index for
  2025-2026. Not usable at all.
- **Wayback — `getdeploying.com/reference/cloud-gpu`**: 24 CDX entries exist, but
  the ones checked in the 2026 window (2026-02-19, 2026-04-13) return Wayback
  playback errors (empty/wrapper page, HTTP 500 on the underlying capture) — the
  site is a client-side-rendered Next.js app and the Wayback crawler did not
  capture the data payload. Not usable.
- **Wayback — `cloud-gpus.com`**: 48 snapshots exist in 2025 but none in 2026;
  given the effort budget and that runpod.io/pricing already yielded structured
  multi-GPU data for the same period, this source was not pursued further (flagged
  here rather than silently skipped).
- **RunPod pricing page, mid-2025 onward redesign**: from ~2025-07 the archived
  page no longer embeds the GraphQL price cache; only a marketing `<meta
  name="description">` tag remains (e.g. "Rent H100 80GB from $1.99/hr, RTX 4090
  from $0.34/hr"). This exact string was found **byte-identical across every
  snapshot from 2025-07 through 2026-06** (13 months) — a hard-coded/stale meta
  tag, not a live price feed. Using it would have silently fabricated a flat
  line, so it was **deliberately excluded** rather than used to "fill" the
  2025-07 → 2026-05 gap.
- **~40% of attempted Wayback snapshot timestamps** (both runpod.io and
  getdeploying.com) returned an archive.org calendar/wrapper page (`<title>Wayback
  Machine</title>`, ~141KB, no site content) instead of the actual capture, even
  though the CDX API reported `statuscode:200`. Retried each at least twice with
  longer spacing; genuine misses were skipped rather than substituted.

## Coverage summary

| Period | Coverage |
|---|---|
| 2025-01 → 2025-06 | Sparse — 7 RunPod on-demand/marketplace snapshots only (H100/H200/B200/A100/L40S/RTX4090) |
| 2025-07 → 2026-05-07 | **Gap** — no verifiable source found (see exclusions above) |
| 2026-05-08 → 2026-07-17 | Dense — daily, 7 providers (runpod, lambda, crusoe, nebius, sfcompute, vast.ai, coreweave×1) |
| 2026-07-17 onward | Covered by this repo's own live collectors, not part of this backfill |

## Top parsing caveats

- Pre-2026-05-08 data in the source GitHub repo is excluded as not credible (frozen
  45-day values sourced from a current-state-only aggregator) — see exclusion note above.
- RunPod/Lambda on-demand prices are published rate cards, not live marketplace
  quotes — expect long flat stretches with occasional step changes; flat ≠ fabricated
  for these two providers specifically.
- `H100 SXM` / `H100 NVL` / `H100 PCIe` and `A100 SXM` / `A100 PCIe` are kept as
  distinct keys (not merged into a single "H100"/"A100") because their prices
  differ meaningfully by form factor.
- RunPod Wayback snapshots after ~2025-07 carry no usable price payload (site
  redesign to client-rendered pricing table); that channel goes dark until this
  repo's own collector picks up 2026-05-08 onward via the GitHub source.
- `vast.ai` rows in the GitHub source are `median_dph`-based marketplace
  snapshots per (gpu, region) — collapsed here to the lowest median across
  regions per day to match this repo's `vast.jsonl` "lowest on-demand-equivalent"
  convention; per-region granularity is available in the raw CSV if needed later
  (not re-fetched/stored here to stay within scope).
