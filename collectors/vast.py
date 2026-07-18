#!/usr/bin/env python3
"""Vast.ai collector — THE availability signal (hourly).

Queries the Vast.ai public bundles API per GPU class (one request per class,
matching the exact gpu_name string Vast uses) and aggregates offers/total_gpus/
median-p25-min $/GPU-hr. Writes data/latest/vast.json + appends
data/history/vast.jsonl per docs/DATA_CONTRACT.md.
"""
import statistics
import sys
from urllib.parse import quote

from common import atomic_write_json, append_history, fetch_url, iso_utc_now, latest_path
from validation import check_price, check_relations, quarantine

BUNDLES_URL = "https://console.vast.ai/api/v0/bundles/"

GPU_CLASSES = (
    "H100 SXM",
    "H100 NVL",
    "H200",
    "B200",
    "A100 SXM4",
    "RTX 4090",
    "MI300X",
)


def _query_for(gpu_name):
    return {
        "gpu_name": {"eq": gpu_name},
        "rentable": {"eq": True},
        "external": {"eq": False},
        "limit": 300,
    }


def fetch_gpu_class(gpu_name, timeout=25, retries=2):
    """Fetch raw bundles JSON (as text) for one GPU class."""
    url = BUNDLES_URL + "?q=" + quote(__import__("json").dumps(_query_for(gpu_name)))
    return fetch_url(url, timeout=timeout, retries=retries)


def parse_gpu_class(raw_json_text):
    """Pure parse: raw bundles response text -> summary dict for one GPU class.

    Returns {"offers": int, "total_gpus": int, "median_dph": float|None,
    "p25_dph": float|None, "min_dph": float|None}. offers=0 -> all price
    fields None (no offers currently listed for this class).
    """
    import json

    doc = json.loads(raw_json_text)
    offers = doc.get("offers") or []
    total_gpus = 0
    dph_per_gpu = []
    for o in offers:
        n = o.get("num_gpus") or 1
        dph_total = o.get("dph_total")
        try:
            n = int(n)
        except (TypeError, ValueError):
            n = 1
        if n < 1:
            n = 1
        total_gpus += n
        if dph_total is not None:
            try:
                dph_per_gpu.append(float(dph_total) / n)
            except (TypeError, ValueError, ZeroDivisionError):
                pass

    n_offers = len(offers)
    if dph_per_gpu:
        dph_per_gpu.sort()
        median_dph = round(statistics.median(dph_per_gpu), 4)
        min_dph = round(dph_per_gpu[0], 4)
        # p25 via nearest-rank on the sorted list
        idx = max(0, int(round(0.25 * (len(dph_per_gpu) - 1))))
        p25_dph = round(dph_per_gpu[idx], 4)
    else:
        median_dph = min_dph = p25_dph = None

    return {
        "offers": n_offers,
        "total_gpus": total_gpus,
        "median_dph": median_dph,
        "p25_dph": p25_dph,
        "min_dph": min_dph,
    }


def _validate_and_maybe_quarantine(gpu_name, summary):
    """Check one GPU class's summary against the price bands + relation
    invariants. Returns (keep: bool, note: str|None). On any price-band
    violation the whole class summary is quarantined and excluded (never
    silently included). Relation violations quarantine the implausible
    member field(s) when unambiguous; otherwise only a warning is emitted
    and the summary is kept.
    """
    price_fields = ("median_dph", "p25_dph", "min_dph")
    violations = []
    for field in price_fields:
        v = summary.get(field)
        if v is None:
            continue
        result = check_price(gpu_name, v)
        if result != "ok":
            violations.append(result)

    if violations:
        quarantine("vast", {"gpu_name": gpu_name, **summary}, "; ".join(violations))
        return False, f"{gpu_name}: quarantined (price band violation: {'; '.join(violations)})"

    rel_record = {
        "p25_dph": summary.get("p25_dph"),
        "median_dph": summary.get("median_dph"),
        "offers": summary.get("offers"),
        "total_gpus": summary.get("total_gpus"),
    }
    rel_violations = check_relations(rel_record)
    if rel_violations:
        # p25 <= median is well-defined which field is "implausible" only in
        # combination (median already validated above), so this is ambiguous
        # by nature -> quarantine nothing, just warn per the spec.
        return True, f"{gpu_name}: relation_warning: {'; '.join(rel_violations)}"

    return True, None


def collect():
    """Fetch + parse every GPU class, isolating per-class failures into errors[].
    Every class summary is validated (price bands + relation invariants)
    before being included; failures are excluded + quarantined, never
    silently included.
    """
    gpus = {}
    errors = []
    n_quarantined = 0
    for gpu_name in GPU_CLASSES:
        try:
            raw = fetch_gpu_class(gpu_name)
            summary = parse_gpu_class(raw)
        except Exception as e:  # noqa: BLE001
            errors.append({"gpu_name": gpu_name, "error": repr(e)})
            print(f"[vast] {gpu_name} ERROR: {e}", file=sys.stderr)
            continue

        keep, note = _validate_and_maybe_quarantine(gpu_name, summary)
        if keep:
            gpus[gpu_name] = summary
            if note:
                errors.append({"gpu_name": gpu_name, "warning": note})
        else:
            n_quarantined += 1
            errors.append({"gpu_name": gpu_name, "error": note})

    if n_quarantined:
        errors.append({"note": f"quarantined {n_quarantined} items"})

    return {"asof": iso_utc_now(), "gpus": gpus, "errors": errors}


def write(payload):
    atomic_write_json(latest_path("vast"), payload)
    hist_gpus = {
        g: {"offers": s.get("offers"), "median_dph": s.get("median_dph")}
        for g, s in payload.get("gpus", {}).items()
    }
    append_history("vast", {"ts": payload["asof"], "gpus": hist_gpus})


def main():
    payload = collect()
    write(payload)
    n_ok = len(payload["gpus"])
    n_err = len(payload["errors"])
    print(f"[vast] wrote {latest_path('vast')} ({n_ok} classes ok, {n_err} errors)")
    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
