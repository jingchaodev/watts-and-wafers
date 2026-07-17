#!/usr/bin/env python3
"""Neocloud collector — RunPod + DataCrunch lowest on-demand $/GPU-hr (hourly).

Ported from /root/.claude/skills/automation/wiki-web/gpu_snapshot.py (same
endpoints/parsing), simplified down to "lowest on-demand $/hr per normalized
GPU name" per docs/DATA_CONTRACT.md's neoclouds.json shape:
    {"asof": "...", "providers": {"runpod": {"H100": 2.19, ...}, "datacrunch": {...}}, "errors": []}
"""
import html
import json
import re
import sys

from common import atomic_write_json, append_history, fetch_url, iso_utc_now, latest_path

RUNPOD_GRAPHQL_URL = "https://api.runpod.io/graphql"
DATACRUNCH_PRICING_URL = "https://datacrunch.io/pricing"

WATCH_GPUS = ("GB200", "B300", "B200", "GH200", "H200", "H100", "A100", "L40S", "RTX 4090", "MI300X")

RUNPOD_QUERY = """
{
  gpuTypes {
    id displayName memoryInGb secureCloud communityCloud
    lowestPrice(input:{gpuCount:1}) { minimumBidPrice uninterruptablePrice }
  }
}
"""


def norm_gpu(name):
    """Normalize a free-text GPU label to one of the contract's canonical names."""
    s = (name or "").upper().replace("NVIDIA", "").strip()
    for g in WATCH_GPUS:
        if g in s:
            return g
    return None


def gpu_count_from_name(name):
    m = re.search(r"\b(\d+)x\b", name or "", re.I)
    return int(m.group(1)) if m else 1


# ---------------------------------------------------------------------------
# RunPod
# ---------------------------------------------------------------------------

def fetch_runpod(timeout=25, retries=2):
    return fetch_url(RUNPOD_GRAPHQL_URL, method="POST", body={"query": RUNPOD_QUERY},
                      timeout=timeout, retries=retries)


def parse_runpod(raw_json_text):
    """Pure parse: RunPod GraphQL response text -> {gpu_name: lowest_on_demand_$/hr}."""
    doc = json.loads(raw_json_text)
    gpu_types = (doc.get("data") or {}).get("gpuTypes") or []
    best = {}
    for x in gpu_types:
        label = (x.get("displayName") or "") + " " + (x.get("id") or "")
        gpu = norm_gpu(label)
        if not gpu:
            continue
        lp = x.get("lowestPrice") or {}
        # "on-demand" = uninterruptablePrice; fall back to bid price only if
        # on-demand isn't published (still real $/hr a renter could pay).
        price = lp.get("uninterruptablePrice")
        if price is None:
            price = lp.get("minimumBidPrice")
        if price is None:
            continue
        price = float(price)
        if gpu not in best or price < best[gpu]:
            best[gpu] = price
    return {g: round(p, 4) for g, p in best.items()}


# ---------------------------------------------------------------------------
# DataCrunch
# ---------------------------------------------------------------------------

def fetch_datacrunch(timeout=25, retries=2):
    return fetch_url(DATACRUNCH_PRICING_URL, timeout=timeout, retries=retries)


def parse_datacrunch(raw_html_text):
    """Pure parse: DataCrunch pricing page HTML -> {gpu_name: lowest_on_demand_$/hr}.

    Scrapes the page's JSON-LD (@type Offer) blocks. Offer names look like
    "1x H100 SXM5 80GB on-demand" / "... spot" — we only keep on-demand.
    """
    scripts = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        raw_html_text, flags=re.I | re.S,
    )
    best = {}
    for s in scripts:
        try:
            doc = json.loads(html.unescape(s.strip()))
        except Exception:
            continue
        graph = doc.get("@graph") if isinstance(doc, dict) else None
        if not graph:
            continue
        for o in graph:
            if o.get("@type") != "Offer":
                continue
            name = o.get("name") or ""
            if "on-demand" not in name.lower():
                continue  # neoclouds.json wants on-demand only
            gpu = norm_gpu(name)
            if not gpu:
                continue
            price = o.get("price")
            if price is None:
                continue
            cnt = gpu_count_from_name(name)
            try:
                per_gpu = float(price) / max(cnt, 1)
            except (TypeError, ValueError):
                continue
            if gpu not in best or per_gpu < best[gpu]:
                best[gpu] = per_gpu
    return {g: round(p, 4) for g, p in best.items()}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def collect():
    providers = {}
    errors = []
    for key, fetch_fn, parse_fn in (
        ("runpod", fetch_runpod, parse_runpod),
        ("datacrunch", fetch_datacrunch, parse_datacrunch),
    ):
        try:
            raw = fetch_fn()
            providers[key] = parse_fn(raw)
        except Exception as e:  # noqa: BLE001
            errors.append({"provider": key, "error": repr(e)})
            print(f"[neoclouds] {key} ERROR: {e}", file=sys.stderr)
    return {"asof": iso_utc_now(), "providers": providers, "errors": errors}


def write(payload):
    atomic_write_json(latest_path("neoclouds"), payload)
    append_history("neoclouds", {"ts": payload["asof"], "providers": payload.get("providers", {})})


def main():
    payload = collect()
    write(payload)
    n_ok = len(payload["providers"])
    n_err = len(payload["errors"])
    print(f"[neoclouds] wrote {latest_path('neoclouds')} ({n_ok} providers ok, {n_err} errors)")
    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
