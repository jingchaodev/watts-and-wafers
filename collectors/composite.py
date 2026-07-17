#!/usr/bin/env python3
"""Composite demand-index collector — combines the other 4 signals (every run).

Reads the trailing history written by vast/neoclouds/openrouter/memory
(data/history/*.jsonl) and computes 4 z-scored signals per
docs/DATA_CONTRACT.md, then blends them into a single 0-100 index:

    index = 50 + 12.5 * sum(weight * z for each signal), clamped to [0, 100]

Signals (weight, meaning):
  gpu_availability (0.35) -- from vast.jsonl: current mean H100-class offers
      (H100 SXM + H100 NVL) vs. the trailing-30d mean/stdev of that same
      series. FEWER offers = tighter market = positive z (we negate the raw
      z so "offers falling" reads as demand tightening, per the contract's
      "falling offers + rising median = demand tightening" framing).
  gpu_price (0.15) -- from vast.jsonl: mean H100-class median_dph over the
      trailing 7d vs. the trailing 30d mean/stdev. Rising price = positive z.
  token_economics (0.25) -- from openrouter.jsonl: frontier_median_completion
      trend over 30d, z of the most recent value vs. the 30d mean/stdev,
      NEGATED (frontier price falling = commoditization pressure easing =
      *demand* tightening in the Baker "cost curve" framing used here: falling
      cost per token means more inference is being run per dollar, i.e. token
      demand growing faster than supply/price would otherwise allow).
  memory (0.25) -- from memory.jsonl: DDR5 (2Gx8) 4800/5600 avg spot price,
      most recent 7d mean vs. trailing 30d mean/stdev. Rising price = positive z.

All z-scores are guarded: if the history has fewer than MIN_HISTORY points,
or the trailing stdev is 0 (flat/insufficient data), z=0 and direction="flat"
rather than raising or dividing by zero.
"""
import statistics
import sys

from common import atomic_write_json, append_history, iso_utc_now, latest_path, read_history

MIN_HISTORY = 5

WEIGHTS = {
    "gpu_availability": 0.35,
    "token_economics": 0.25,
    "memory": 0.25,
    "gpu_price": 0.15,
}

H100_CLASSES = ("H100 SXM", "H100 NVL")
DDR5_ITEM = "DDR5 16Gb (2Gx8) 4800/5600"

LABEL_THRESHOLDS = (
    (65, "SURGING"),
    (55, "TIGHTENING"),
    (45, "NEUTRAL"),
    (35, "SOFTENING"),
)


def _zscore(value, series):
    """z of `value` against mean/stdev of `series`. Guards short/flat series."""
    if value is None or len(series) < MIN_HISTORY:
        return 0.0
    try:
        mean = statistics.mean(series)
        stdev = statistics.pstdev(series)
    except statistics.StatisticsError:
        return 0.0
    if stdev == 0:
        return 0.0
    return (value - mean) / stdev


def _direction(z, eps=0.15):
    if z > eps:
        return "up"
    if z < -eps:
        return "down"
    return "flat"


def _h100_offers(gpus_dict):
    total = 0
    any_present = False
    for k in H100_CLASSES:
        entry = gpus_dict.get(k)
        if entry and entry.get("offers") is not None:
            total += entry["offers"]
            any_present = True
    return total if any_present else None


def _h100_median_dph(gpus_dict):
    vals = []
    for k in H100_CLASSES:
        entry = gpus_dict.get(k)
        if entry and entry.get("median_dph") is not None:
            vals.append(entry["median_dph"])
    return statistics.mean(vals) if vals else None


def compute_gpu_availability(vast_hist):
    """-(z of current mean H100-class offers vs trailing 30d)."""
    series = [_h100_offers(h.get("gpus", {})) for h in vast_hist]
    series = [v for v in series if v is not None]
    if not series or len(series) < MIN_HISTORY:
        return {"z": 0.0, "direction": "flat", "detail": "insufficient history"}
    current = series[-1]
    raw_z = _zscore(current, series[:-1] or series)
    z = round(-raw_z, 3)
    direction = _direction(z)
    pct = None
    if len(series) >= 2 and series[-2]:
        pct = round(100.0 * (series[-1] - series[-2]) / series[-2], 1)
    detail = f"H100-class offers {current} ({'%+.1f%%' % pct if pct is not None else 'n/a'} vs prior)"
    return {"z": z, "direction": direction, "detail": detail}


def compute_gpu_price(vast_hist):
    """z of trailing-7d mean H100-class median_dph vs trailing-30d mean/stdev."""
    series = [_h100_median_dph(h.get("gpus", {})) for h in vast_hist]
    series = [v for v in series if v is not None]
    if not series or len(series) < MIN_HISTORY:
        return {"z": 0.0, "direction": "flat", "detail": "insufficient history"}
    window7 = series[-7:] if len(series) >= 7 else series
    recent_mean = statistics.mean(window7)
    z = round(_zscore(recent_mean, series), 3)
    direction = _direction(z)
    detail = f"H100-class median $/hr {round(recent_mean, 2)} (7d mean)"
    return {"z": z, "direction": direction, "detail": detail}


def compute_token_economics(openrouter_hist):
    """-(z of latest frontier_median_completion_usd_per_m vs trailing 30d)."""
    series = [
        h.get("frontier_median_completion_usd_per_m")
        for h in openrouter_hist
        if h.get("frontier_median_completion_usd_per_m") is not None
    ]
    if not series or len(series) < MIN_HISTORY:
        return {"z": 0.0, "direction": "flat", "detail": "insufficient history"}
    current = series[-1]
    raw_z = _zscore(current, series[:-1] or series)
    z = round(-raw_z, 3)
    direction = _direction(z)
    detail = f"frontier $/M completion {current} (latest)"
    return {"z": z, "direction": direction, "detail": detail}


def _ddr5_avg(dram_spot_list):
    for row in dram_spot_list or []:
        if row.get("item") == DDR5_ITEM:
            return row.get("avg")
    return None


def compute_memory(memory_hist):
    """z of trailing-7d mean DDR5 spot avg vs trailing-30d mean/stdev."""
    series = [_ddr5_avg(h.get("dram_spot")) for h in memory_hist]
    series = [v for v in series if v is not None]
    if not series or len(series) < MIN_HISTORY:
        return {"z": 0.0, "direction": "flat", "detail": "insufficient history"}
    window7 = series[-7:] if len(series) >= 7 else series
    recent_mean = statistics.mean(window7)
    z = round(_zscore(recent_mean, series), 3)
    direction = _direction(z)
    detail = f"DDR5 16Gb spot avg {round(recent_mean, 3)} (7d mean)"
    return {"z": z, "direction": direction, "detail": detail}


def compute_index(signal_map):
    """Pure: {"gpu_availability": {...}, ...} -> (index, label, signals[]).

    signal_map values are {"z", "direction", "detail"} dicts keyed by the
    4 signal names in WEIGHTS.
    """
    total = 0.0
    signals = []
    for key, weight in WEIGHTS.items():
        s = signal_map.get(key) or {"z": 0.0, "direction": "flat", "detail": "n/a"}
        z = s.get("z") or 0.0
        total += weight * z
        signals.append({
            "key": key,
            "weight": weight,
            "z": z,
            "direction": s.get("direction", "flat"),
            "detail": s.get("detail", "n/a"),
        })

    index = 50 + 12.5 * total
    index = max(0.0, min(100.0, index))
    index = round(index, 2)

    label = "GLUT"
    for threshold, name in LABEL_THRESHOLDS:
        if index >= threshold:
            label = name
            break

    return index, label, signals


def collect():
    vast_hist = read_history("vast")
    openrouter_hist = read_history("openrouter")
    memory_hist = read_history("memory")

    signal_map = {
        "gpu_availability": compute_gpu_availability(vast_hist),
        "gpu_price": compute_gpu_price(vast_hist),
        "token_economics": compute_token_economics(openrouter_hist),
        "memory": compute_memory(memory_hist),
    }

    index, label, signals = compute_index(signal_map)

    return {
        "asof": iso_utc_now(),
        "index": index,
        "label": label,
        "signals": signals,
    }


def write(payload):
    atomic_write_json(latest_path("composite"), payload)
    append_history("composite", {
        "ts": payload["asof"],
        "index": payload.get("index"),
        "label": payload.get("label"),
    })


def main():
    payload = collect()
    write(payload)
    print(f"[composite] wrote {latest_path('composite')} "
          f"(index={payload['index']}, label={payload['label']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
