#!/usr/bin/env python3
"""Data-validation layer for Watts & Wafers collectors (stdlib-only).

Three jobs, per the task's invariant-gates-at-ingest design:
  1. `check_price`     — plausibility bands per GPU class (unit-error catcher).
  2. `check_relations`  — cross-field sanity within one record (spot/on-demand,
                          p25/median, offers >= 0).
  3. `quarantine`       — append a JSON line for anything excluded from output,
                          so nothing is silently dropped.

INTEGRATION (for neoclouds.py — wired by the orchestrator, not this agent):
    from validation import filter_prices, quarantine  # noqa: F401
    providers[key] = filter_prices("neoclouds", parse_fn(raw), quarantine_source=key)
That's it: one import + one filter call around each provider's parsed
{gpu_name: price} dict before it goes into the `providers` dict that gets
written. `filter_prices` returns the same shape with bad entries removed,
and quarantines the removed entries itself.
"""
import json
import os
import re

from common import DATA_HISTORY, iso_utc_now

QUARANTINE_PATH = os.path.join(DATA_HISTORY, "quarantine.jsonl")

# ---------------------------------------------------------------------------
# Price plausibility bands ($/GPU-hr)
#
# Deliberately WIDE — these exist to catch unit errors (per-node price
# reported as per-GPU, cents mistaken for dollars, a stray $/month value,
# etc.), not to flag real market price moves. A GPU-hr at $0.04 or $45 is
# almost certainly a parsing/unit bug, not a legitimate market print.
# ---------------------------------------------------------------------------
PRICE_BANDS_USD_PER_GPU_HR = {
    "H100": (0.5, 16),
    "H200": (0.8, 20),
    "B200": (1.5, 25),
    "GB200": (2, 40),
    "A100": (0.2, 8),
    "L40S": (0.2, 4),
    "RTX 4090": (0.05, 2),
    "MI300X": (0.5, 10),
}

# Free-text/collector-specific GPU class labels -> canonical band key.
# Longest/most-specific patterns first so e.g. "H100 SXM" doesn't collide
# with a bare "H100" entry check order (dict iteration below handles this
# via substring search over a tuple ordered most-specific first).
_CLASS_ALIASES = (
    (re.compile(r"GB200", re.I), "GB200"),
    (re.compile(r"H100", re.I), "H100"),
    (re.compile(r"H200", re.I), "H200"),
    (re.compile(r"B200", re.I), "B200"),
    (re.compile(r"A100", re.I), "A100"),
    (re.compile(r"L40S", re.I), "L40S"),
    (re.compile(r"RTX\s*4090|4090", re.I), "RTX 4090"),
    (re.compile(r"MI300X", re.I), "MI300X"),
)


def canonical_gpu_class(gpu_class):
    """Map a free-text GPU label (e.g. 'H100 SXM', 'A100 SXM4') to the
    canonical key used in PRICE_BANDS_USD_PER_GPU_HR. Returns None if no
    band is known for it (caller should treat as "no check available", not
    a violation)."""
    if not gpu_class:
        return None
    s = str(gpu_class)
    for rx, canon in _CLASS_ALIASES:
        if rx.search(s):
            return canon
    return None


def check_price(gpu_class, usd_per_gpu_hr):
    """Return "ok" if usd_per_gpu_hr falls within the plausibility band for
    gpu_class, else a violation string describing why. None/non-numeric
    prices are "ok" (nothing to check — absence is handled elsewhere per
    the data contract, not a validation failure). An unrecognized gpu_class
    is also "ok" (no band defined, so nothing to enforce)."""
    if usd_per_gpu_hr is None:
        return "ok"
    try:
        price = float(usd_per_gpu_hr)
    except (TypeError, ValueError):
        return f"non-numeric price: {usd_per_gpu_hr!r}"

    canon = canonical_gpu_class(gpu_class)
    if canon is None:
        return "ok"  # no band defined for this class; nothing to enforce

    lo, hi = PRICE_BANDS_USD_PER_GPU_HR[canon]
    if price < lo:
        return f"{gpu_class}: ${price:.4f}/gpu-hr below plausibility floor ${lo} (canon={canon})"
    if price > hi:
        return f"{gpu_class}: ${price:.4f}/gpu-hr above plausibility ceiling ${hi} (canon={canon})"
    return "ok"


def check_relations(record):
    """Spot-check cross-field relationships within one record. `record` is a
    dict that may contain any of: spot_dph/ondemand_dph (or spot_vm_hr/
    ondemand_vm_hr), p25_dph/median_dph, offers/total_gpus. Only checks
    fields that are actually present (both-present pairs); missing fields
    are silently skipped, not flagged.

    Returns a list of violation strings (empty list = no violations).
    """
    violations = []

    spot = _first_present(record, ("spot_dph", "spot_vm_hr", "spot_gpu_hr"))
    ondemand = _first_present(record, ("ondemand_dph", "ondemand_vm_hr", "ondemand_gpu_hr", "on_demand_dph"))
    if spot is not None and ondemand is not None:
        try:
            spot_f, ondemand_f = float(spot), float(ondemand)
            if spot_f > ondemand_f * 1.05:
                violations.append(
                    f"spot ({spot_f}) > on-demand ({ondemand_f}) * 1.05 — spot should not exceed on-demand"
                )
        except (TypeError, ValueError):
            pass

    p25 = _first_present(record, ("p25_dph", "p25"))
    median = _first_present(record, ("median_dph", "median"))
    if p25 is not None and median is not None:
        try:
            p25_f, median_f = float(p25), float(median)
            if p25_f > median_f:
                violations.append(f"p25 ({p25_f}) > median ({median_f}) — p25 must be <= median")
            # "reasonable" upper check: median shouldn't dwarf p25 by more
            # than a wide 10x (catches a scrambled/duplicated field, not
            # normal market dispersion).
            if p25_f > 0 and median_f > p25_f * 10:
                violations.append(f"median ({median_f}) > 10x p25 ({p25_f}) — implausible spread")
        except (TypeError, ValueError):
            pass

    offers = _first_present(record, ("offers", "n_offers"))
    if offers is not None:
        try:
            if float(offers) < 0:
                violations.append(f"offers ({offers}) < 0")
        except (TypeError, ValueError):
            pass

    total_gpus = record.get("total_gpus")
    if total_gpus is not None:
        try:
            if float(total_gpus) < 0:
                violations.append(f"total_gpus ({total_gpus}) < 0")
        except (TypeError, ValueError):
            pass

    return violations


def _first_present(record, keys):
    for k in keys:
        if k in record and record[k] is not None:
            return record[k]
    return None


def quarantine(source, item, reason):
    """Append one JSON line to data/history/quarantine.jsonl: atomic append
    (single write() call under 'a' mode; each line is independently valid
    JSON so partial-write torn-line risk is the same as append_history's
    existing pattern elsewhere in this codebase).

    source: collector/provider name, e.g. "vast", "neoclouds:runpod".
    item:   the offending record/value (must be JSON-serializable).
    reason: human-readable reason string.
    """
    os.makedirs(os.path.dirname(QUARANTINE_PATH), exist_ok=True)
    line = {
        "ts": iso_utc_now(),
        "source": source,
        "item": item,
        "reason": reason,
    }
    with open(QUARANTINE_PATH, "a") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def filter_prices(source, gpu_price_dict, quarantine_source=None):
    """Convenience wrapper for the common "{gpu_name: price}" shape used by
    neoclouds.py-style collectors: runs check_price on every entry, drops +
    quarantines any that fail, and returns the cleaned dict.

    quarantine_source overrides `source` in the quarantine record only
    (e.g. pass the provider key, "runpod"/"datacrunch", while `source`
    stays "neoclouds" for logging); defaults to `source`.
    """
    qsource = quarantine_source or source
    clean = {}
    n_quarantined = 0
    for gpu_name, price in (gpu_price_dict or {}).items():
        result = check_price(gpu_name, price)
        if result == "ok":
            clean[gpu_name] = price
        else:
            quarantine(qsource, {"gpu": gpu_name, "price": price}, result)
            n_quarantined += 1
    return clean
