# Watts & Wafers

AI compute demand signals, on one tape: GPU rental **price + availability**, **token
economics**, and **memory spot prices** — the physical-stack demand tells (watts & wafers)
that lead AI capex sentiment.

Inspired by how Gavin Baker reads AI demand: availability (sold-out %) and token-consumption
acceleration rank above price. Most dashboards track price only; this one tracks scarcity.

## How it works

```
VPS cron → collectors/*.py (stdlib Python)
         → data/latest/*.json + data/history/*.jsonl (committed to this repo)
         → Vercel rebuilds web/ (Next.js, fully static) on every push
```

- No database. Git history is the time series.
- No secrets in this repo. Optional API keys live on the collector host only.
- A failing source degrades gracefully (`errors[]` + stale marker), never breaks the site.

## Signals (v1)

| Signal | Source | Cadence |
|---|---|---|
| GPU availability (offer count) + marketplace price | Vast.ai public API | hourly |
| Neocloud on-demand $/GPU-hr | RunPod, DataCrunch | hourly |
| Hyperscaler $/GPU-hr (on-demand + spot) | Azure Retail Prices API | daily |
| Model cost / Pareto ($/M tokens) | OpenRouter models API | daily |
| DRAM spot, NAND weekly note | TrendForce public pages | daily |
| Composite demand index (0–100) | z-scores over history | every run |

Data contract between collectors and site: [`docs/DATA_CONTRACT.md`](docs/DATA_CONTRACT.md).

## Develop

```bash
# collectors
python3 collectors/run.py --group hourly   # or: daily
python3 -m pytest collectors/tests -q

# site
cd web && npm install && npm run dev
```

## Deploy

Vercel → Import this repo → set **Root Directory = `web`**. Every data push redeploys.
