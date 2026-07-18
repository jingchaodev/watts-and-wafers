#!/usr/bin/env python3
"""Cross-source deviation flags (runs in the daily group, alongside the other
collectors). Reads the latest on-demand $/GPU-hr each provider reported
(vast median, neoclouds providers, hyperscaler/azure) and, for each GPU
class, flags any single provider whose price is off by more than 2.5x
(either direction) from the cohort median across providers.

This is informational only — it does not gate/exclude anything from the
other collectors' outputs (that's validation.py's job at ingest time). It
surfaces disagreements between independently-sourced prices for a human (or
the site) to look at. Writes data/latest/crosscheck.json per this shape:
    {"asof": "...", "flags": [{"gpu", "provider", "price",
                                "cohort_median", "ratio"}], "errors": []}
No flags found -> "flags": [].
"""
import math
import statistics
import sys

from common import atomic_write_json, iso_utc_now, latest_path
from validation import canonical_gpu_class

# |log-deviation| > ln(2.5) means the price is more than 2.5x off the
# cohort median (in either direction).
LOG_DEVIATION_THRESHOLD = math.log(2.5)


def _read_latest(name):
    """Read data/latest/<name>.json, returning {} if missing/unreadable
    (a missing upstream file is a normal degraded state, not a crash)."""
    import json
    path = latest_path(name)
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def gather_prices(vast_doc, neoclouds_doc, hyperscaler_doc):
    """Pure: the three collectors' latest payloads -> {canonical_gpu:
    {provider: price}}. Vast contributes its own per-class median_dph
    (labeled "vast") into the cohort; neoclouds contributes each of its
    providers; hyperscaler contributes "azure" via ondemand_gpu_hr.
    """
    by_gpu = {}

    for gpu_name, summary in (vast_doc.get("gpus") or {}).items():
        canon = canonical_gpu_class(gpu_name)
        price = summary.get("median_dph") if isinstance(summary, dict) else None
        if canon is None or price is None:
            continue
        by_gpu.setdefault(canon, {})["vast"] = float(price)

    for provider, gpu_prices in (neoclouds_doc.get("providers") or {}).items():
        for gpu_name, price in (gpu_prices or {}).items():
            canon = canonical_gpu_class(gpu_name)
            if canon is None or price is None:
                continue
            by_gpu.setdefault(canon, {})[provider] = float(price)

    for sku, entry in (hyperscaler_doc.get("azure") or {}).items():
        gpu_name = entry.get("gpu")
        price = entry.get("ondemand_gpu_hr")
        canon = canonical_gpu_class(gpu_name)
        if canon is None or price is None:
            continue
        # Multiple Azure SKUs can map to the same GPU (different regions);
        # keep the lowest, consistent with "on-demand" meaning "best available".
        cur = by_gpu.setdefault(canon, {}).get("azure")
        if cur is None or price < cur:
            by_gpu[canon]["azure"] = float(price)

    return by_gpu


def compute_flags(by_gpu):
    """Pure: {gpu: {provider: price}} -> list of flag dicts. Cohort median
    is computed across all providers reporting that GPU class; a class
    needs >= 2 providers for any deviation to be meaningful (with only 1
    provider, price == median always, so it's naturally a no-op)."""
    flags = []
    for gpu in sorted(by_gpu.keys()):
        prices_by_provider = by_gpu[gpu]
        prices = list(prices_by_provider.values())
        if len(prices) < 2:
            continue
        cohort_median = statistics.median(prices)
        if cohort_median <= 0:
            continue
        for provider in sorted(prices_by_provider.keys()):
            price = prices_by_provider[provider]
            if price <= 0:
                continue
            log_dev = math.log(price / cohort_median)
            if abs(log_dev) > LOG_DEVIATION_THRESHOLD:
                flags.append({
                    "gpu": gpu,
                    "provider": provider,
                    "price": round(price, 4),
                    "cohort_median": round(cohort_median, 4),
                    "ratio": round(price / cohort_median, 3),
                })
    return flags


def collect():
    errors = []
    vast_doc = _read_latest("vast")
    neoclouds_doc = _read_latest("neoclouds")
    hyperscaler_doc = _read_latest("hyperscaler")

    if not vast_doc:
        errors.append({"source": "vast", "error": "latest/vast.json missing or unreadable"})
    if not neoclouds_doc:
        errors.append({"source": "neoclouds", "error": "latest/neoclouds.json missing or unreadable"})
    if not hyperscaler_doc:
        errors.append({"source": "hyperscaler", "error": "latest/hyperscaler.json missing or unreadable"})

    by_gpu = gather_prices(vast_doc, neoclouds_doc, hyperscaler_doc)
    flags = compute_flags(by_gpu)

    return {"asof": iso_utc_now(), "flags": flags, "errors": errors}


def write(payload):
    atomic_write_json(latest_path("crosscheck"), payload)


def main():
    payload = collect()
    write(payload)
    n_flags = len(payload["flags"])
    n_err = len(payload["errors"])
    print(f"[crosscheck] wrote {latest_path('crosscheck')} ({n_flags} flags, {n_err} errors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
