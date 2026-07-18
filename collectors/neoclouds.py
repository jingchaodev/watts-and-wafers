#!/usr/bin/env python3
"""Neocloud collector — lowest on-demand $/GPU-hr across 6 neocloud providers
(hourly): RunPod, DataCrunch, Lambda, Nebius, Crusoe, CoreWeave.

RunPod + DataCrunch ported from /root/.claude/skills/automation/wiki-web/
gpu_snapshot.py. Lambda/Nebius/Crusoe/CoreWeave ported+adapted from the public
gpu-pricing-tracker repo (github.com/cherielilili/gpu-pricing-tracker) so our
forward tape no longer depends on that tracker's own collection — its regexes
targeted a differently-rendered page for each of these three (Lambda/Nebius
patterns assumed an escaped-JSON-in-HTML blob; the live pages are plain
server-rendered HTML), so the parsers below were rewritten against each
provider's live page rather than copied verbatim. CoreWeave has no fetcher in
that repo (broke after one day per the porting brief); built fresh here since
coreweave.com/pricing turned out to be fully static/parseable.

Simplified down to "lowest on-demand $/hr per normalized GPU name" per
docs/DATA_CONTRACT.md's neoclouds.json shape:
    {"asof": "...", "providers": {"runpod": {"H100": 2.19, ...}, "datacrunch": {...}}, "errors": []}
"""
import html
import json
import re
import sys

from common import atomic_write_json, append_history, fetch_url, iso_utc_now, latest_path
from validation import filter_prices

RUNPOD_GRAPHQL_URL = "https://api.runpod.io/graphql"
DATACRUNCH_PRICING_URL = "https://datacrunch.io/pricing"
LAMBDA_PRICING_URL = "https://lambda.ai/service/gpu-cloud"
NEBIUS_PRICING_URL = "https://nebius.com/prices"
CRUSOE_PRICING_URL = "https://crusoe.ai/cloud/pricing/"
COREWEAVE_PRICING_URL = "https://www.coreweave.com/pricing"

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
# Lambda Labs
# ---------------------------------------------------------------------------

def fetch_lambda(timeout=25, retries=2):
    return fetch_url(LAMBDA_PRICING_URL, timeout=timeout, retries=retries)


LAMBDA_ROW_RE = re.compile(
    r'<tr class="_pricingRow[^"]*"\s+data-plan="([^"]+)">(.*?)</tr>', re.S,
)
LAMBDA_PRICE_RE = re.compile(r'PRICE/GPU/HR\*?">\$([0-9]+\.[0-9]+)')


def parse_lambda(raw_html_text):
    """Pure parse: Lambda GPU cloud pricing page HTML -> {gpu_name: lowest_on_demand_$/hr}.

    Live page (verified 2026-07) renders one <tr data-plan="NVIDIA <model>">
    per instance size, each with its own "PRICE/GPU/HR*" cell inside the same
    row -- no cross-row proximity pairing needed (the upstream tracker's
    regex assumed an escaped-JSON blob and paired price cells to the nearest
    preceding label by character offset; the live HTML is simpler than that).
    """
    best = {}
    for m in LAMBDA_ROW_RE.finditer(raw_html_text):
        plan, row = m.group(1), m.group(2)
        gpu = norm_gpu(plan)
        if not gpu:
            continue
        pm = LAMBDA_PRICE_RE.search(row)
        if not pm:
            continue
        try:
            price = float(pm.group(1))
        except ValueError:
            continue
        if gpu not in best or price < best[gpu]:
            best[gpu] = price
    return {g: round(p, 4) for g, p in best.items()}


# ---------------------------------------------------------------------------
# Nebius
# ---------------------------------------------------------------------------

def fetch_nebius(timeout=25, retries=2):
    return fetch_url(NEBIUS_PRICING_URL, timeout=timeout, retries=retries)


NEBIUS_ROW_RE = re.compile(
    r'<div class="pc-highlight-table-block__row">(.*?)</div></div></div>', re.S,
)
NEBIUS_CELL_RE = re.compile(r'<p>(.*?)</p>', re.S)


def parse_nebius(raw_html_text):
    """Pure parse: Nebius pricing page HTML -> {gpu_name: lowest_on_demand_$/hr}.

    Live page (verified 2026-07) renders the GPU table as
    pc-highlight-table-block__row divs, 5 cells per row:
    Item / vCPUs / RAM / Preemptible-per-GPU-hr / On-demand-per-GPU-hr.
    The upstream tracker's regex targeted an escaped-JSON array
    (["NVIDIA HGX B200","20","224","$5.50"]) which doesn't appear on the live
    page -- rewritten against the actual rendered table. Rows with no
    published on-demand price (e.g. "Contact us" for NVL72 racks) are
    skipped, not a parse failure.
    """
    best = {}
    for m in NEBIUS_ROW_RE.finditer(raw_html_text):
        cells = [html.unescape(c).strip() for c in NEBIUS_CELL_RE.findall(m.group(1))]
        if len(cells) != 5:
            continue
        name = cells[0]
        if "NVIDIA" not in name.upper() and "AMD" not in name.upper():
            continue
        gpu = norm_gpu(name)
        if not gpu:
            continue
        pm = re.search(r"\$([0-9]+\.[0-9]+)", cells[4])
        if not pm:
            continue  # "Contact us" / no on-demand price published
        price = float(pm.group(1))
        if gpu not in best or price < best[gpu]:
            best[gpu] = price
    return {g: round(p, 4) for g, p in best.items()}


# ---------------------------------------------------------------------------
# Crusoe
# ---------------------------------------------------------------------------

def fetch_crusoe(timeout=25, retries=2):
    return fetch_url(CRUSOE_PRICING_URL, timeout=timeout, retries=retries)


CRUSOE_CARD_RE = re.compile(
    r'pricing-item-heading">(NVIDIA|AMD)\s+([A-Z0-9]+)</h4>(.*?)</div>\s*</div>', re.S,
)


def parse_crusoe(raw_html_text):
    """Pure parse: Crusoe Cloud pricing page HTML -> {gpu_name: lowest_on_demand_$/hr}.

    Live page (verified 2026-07) renders one card per GPU model:
    <h4 class="pricing-item-heading">NVIDIA H100</h4> ... <p>$3.90/GPU-hr</p>.
    Cards for GB200/B200/MI355X currently publish no on-demand number ("Contact
    sales" link instead of a $ figure) -- those are skipped as "no price
    published", not treated as a parse error.
    """
    best = {}
    for m in re.finditer(r'pricing-item-heading">(NVIDIA|AMD)\s+([A-Z0-9]+)</h4>(.*?)(?=pricing-item-heading">|\Z)', raw_html_text, re.S):
        vendor, gpu_label, tail = m.group(1), m.group(2), m.group(3)
        gpu = norm_gpu(gpu_label)
        if not gpu:
            continue
        pm = re.search(r'\$([0-9]+\.[0-9]+)/GPU-hr', tail[:800])
        if not pm:
            continue  # "Contact sales" card -- no published on-demand price
        price = float(pm.group(1))
        if gpu not in best or price < best[gpu]:
            best[gpu] = price
    return {g: round(p, 4) for g, p in best.items()}


# ---------------------------------------------------------------------------
# CoreWeave
# ---------------------------------------------------------------------------

def fetch_coreweave(timeout=25, retries=2):
    return fetch_url(COREWEAVE_PRICING_URL, timeout=timeout, retries=retries)


COREWEAVE_PRODUCT_RE = re.compile(
    r'data-product="([a-z0-9-]+)"\s+class="table-model-name">([^<]+)</h3>'
    r'\s*</div>\s*<div class="table-v2-cell"><div>([^<]+)</div></div>'
)
COREWEAVE_PRICE_RE = re.compile(
    r'On-Demand Price:\s*<span class="item-value">\$([0-9]+\.[0-9]+)</span>'
)


def parse_coreweave(raw_html_text):
    """Pure parse: CoreWeave pricing page HTML -> {gpu_name: lowest_on_demand_$/hr}.

    Live page (verified 2026-07, no fetcher existed upstream) is fully static:
    each product renders a table row (`data-product="..."` h3, immediately
    followed by its GPU-count cell, e.g. "8" for a standard HGX node) plus a
    text meta block further down with "On-Demand Price: $X / Hour" -- a
    per-NODE price that must be divided by the node's GPU count to get
    $/GPU-hr. Only the FIRST occurrence of each data-product id is used (it
    appears twice on the page: once in the table row, once in the expanded
    meta card; both carry the same numbers).

    GPU-count cells that aren't a plain integer (e.g. GB200/GB300 NVL72 show
    "4^1", a footnoted rack-quarter count) are skipped rather than guessed --
    dividing by the wrong count would silently produce a wrong $/GPU-hr, and
    validation's plausibility bands can't catch every wrong division safely.
    """
    best = {}
    seen_products = set()
    for pm in COREWEAVE_PRODUCT_RE.finditer(raw_html_text):
        product_id, label, count_text = pm.group(1), pm.group(2), pm.group(3).strip()
        if product_id in seen_products:
            continue
        seen_products.add(product_id)
        gpu = norm_gpu(label)
        if not gpu:
            continue
        if not count_text.isdigit():
            continue  # e.g. "4^1" footnoted rack-quarter count -- ambiguous, skip
        gpu_count = int(count_text)
        if gpu_count <= 0:
            continue
        window = raw_html_text[pm.end():pm.end() + 2000]
        price_m = COREWEAVE_PRICE_RE.search(window)
        if not price_m:
            continue  # "N/A" / contact-sales node -- no published on-demand price
        node_price = float(price_m.group(1))
        per_gpu = node_price / gpu_count
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
        ("lambda", fetch_lambda, parse_lambda),
        ("nebius", fetch_nebius, parse_nebius),
        ("crusoe", fetch_crusoe, parse_crusoe),
        ("coreweave", fetch_coreweave, parse_coreweave),
    ):
        try:
            raw = fetch_fn()
            parsed = parse_fn(raw)
            providers[key] = filter_prices("neoclouds", parsed, quarantine_source=key)
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
