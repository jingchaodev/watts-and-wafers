#!/usr/bin/env python3
"""Headline-signals collector — computes the FIVE dashboard cards (every run,
both hourly and daily groups, after composite) per docs/DATA_CONTRACT.md.

Cards (in contract order): h100_price, availability, spot_discount,
gen_ratio, token_growth. Each card is computed independently and a missing
upstream input renders `value: null` + an explanatory `read` — this module
never raises past main() and never drops a card.

Design notes:
  - "Percentile" throughout = percent of a reference window's values that are
    <= the current value (0-100, rounded to nearest int). Guarded: needs >=5
    points or returns None.
  - h100_price splices data/history/vast_backfill.jsonl (external tracker,
    daily points, dating back before our own vast.jsonl existed) with our own
    data/history/vast.jsonl for the 90d percentile window ONLY. Backfill
    points are used only for dates strictly before our own history's first
    timestamp, so once our own series spans >=90d the backfill naturally
    drops out of the trailing window and `provenance` stops being set.
  - availability's percentile is over OWN history only (own offers series
    has no backfill analog — vast_backfill has no `offers` semantics
    comparable to our own totals), and is null until >=14d of own data.
  - spot_discount / gen_ratio / token_growth percentiles are over their own
    respective history series (thin-history guarded to None).
"""
import statistics
import sys
from datetime import datetime, timedelta, timezone

from common import atomic_write_json, iso_utc_now, latest_path, read_history
from validation import check_price

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

H100_CLASSES = ("H100 SXM", "H100 NVL")
WINDOW_DAYS = 90
DIRECTION_DEADBAND_PCT = 2.0  # +/-2% => "flat"
MIN_PERCENTILE_POINTS = 5
MIN_AVAILABILITY_OWN_DAYS = 14

# Perf-adjustment coefficient for gen_ratio: B200 vs H100 decode-throughput
# ratio, conservative MLPerf v5.0 FP4 basis (~3.16x, rounded), NOT the
# best-case ~11x MoE/InferenceX figure — see
# docs/research/perf-coefficients-issue5.md ("Proposed coefficient table").
# Example: B200 $7/hr / 3.2 = $2.19 H100-equivalent price.
B200_H100_PERF_COEFFICIENT = 3.2


def _parse_ts(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def _date_of(ts):
    return ts[:10]


def _round(v, n=4):
    return round(v, n) if v is not None else None


def _pct_change(new, old):
    if new is None or old is None or old == 0:
        return None
    return round(100.0 * (new - old) / old, 2)


def _direction(delta_pct, deadband=DIRECTION_DEADBAND_PCT):
    if delta_pct is None:
        return "flat"
    if delta_pct > deadband:
        return "up"
    if delta_pct < -deadband:
        return "down"
    return "flat"


def _percentile(value, series):
    """% of `series` (any order) that is <= value, 0-100 rounded int.
    None if value is None or series too short."""
    if value is None:
        return None
    series = [v for v in series if v is not None]
    if len(series) < MIN_PERCENTILE_POINTS:
        return None
    n_le = sum(1 for v in series if v <= value)
    return round(100.0 * n_le / len(series))


def _downsample_daily_last(points):
    """[(ts_or_date_str, value), ...] (any granularity, chronological or not)
    -> last-of-day value per date, sorted by date ascending. Points with
    value None are dropped."""
    by_date = {}
    for ts, value in points:
        if value is None or ts is None:
            continue
        d = _date_of(ts)
        # keep the latest-seen value for that date (assumes input roughly
        # chronological; last write wins which matches "last-of-day" when
        # iterated in ts order — callers pass history in chronological order)
        by_date[d] = value
    return sorted(by_date.items())


def _spark(daily_pairs, n=30):
    """[(date, value), ...] chronological -> last n as [[date, value], ...]."""
    tail = daily_pairs[-n:]
    return [[d, v] for d, v in tail]


def _read_latest_json(name):
    import json
    path = latest_path(name)
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


# ---------------------------------------------------------------------------
# h100_price
# ---------------------------------------------------------------------------

def _h100_class_median_of_medians(gpus_dict):
    """Fold H100 SXM + H100 NVL median_dph into one value via median of
    medians (per contract: 'fold SXM/NVL via median of medians'). With <=2
    classes this is just their mean, but statistics.median generalizes if a
    3rd H100-class variant is ever added."""
    vals = []
    for k in H100_CLASSES:
        entry = (gpus_dict or {}).get(k)
        if entry and entry.get("median_dph") is not None:
            vals.append(entry["median_dph"])
    if not vals:
        return None
    return statistics.median(vals)


def _h100_price_point_from_vast_line(line):
    return _h100_class_median_of_medians(line.get("gpus", {}))


def build_h100_price_splice(vast_hist, backfill_hist):
    """Build the spliced daily series used for the 90d percentile window:
    backfill_hist (external tracker, daily points) for dates strictly before
    our own history's earliest date, UNION our own vast_hist daily-downsampled
    points for all dates we have. Returns (daily_pairs, splice_active)."""
    own_pairs = _downsample_daily_last(
        [(h.get("ts"), _h100_price_point_from_vast_line(h)) for h in vast_hist]
    )
    own_dates = {d for d, _ in own_pairs}
    earliest_own_date = min(own_dates) if own_dates else None

    backfill_pairs = _downsample_daily_last(
        [(h.get("ts"), _h100_class_median_of_medians(h.get("gpus", {}))) for h in backfill_hist]
    )
    if earliest_own_date is not None:
        backfill_pairs = [(d, v) for d, v in backfill_pairs if d < earliest_own_date]

    splice_active = bool(backfill_pairs)  # any backfill point actually used
    merged = {d: v for d, v in backfill_pairs}
    merged.update({d: v for d, v in own_pairs})
    return sorted(merged.items()), splice_active


def compute_h100_price(vast_hist, backfill_hist):
    daily_pairs, splice_active = build_h100_price_splice(vast_hist, backfill_hist)
    if not daily_pairs:
        return _null_card(
            "h100_price", "H100 market price", "$/hr",
            "No H100-class price data available yet.",
        )

    current = daily_pairs[-1][1]
    ok = check_price("H100", current)
    if ok != "ok":
        # Surfaced value failed plausibility check -> treat as missing rather
        # than publish a bad number; the underlying quarantine already
        # happened in vast.py at ingest, this is a belt-and-suspenders guard.
        return _null_card(
            "h100_price", "H100 market price", "$/hr",
            f"Latest H100 price failed plausibility check: {ok}",
        )

    window_start = _date_of(daily_pairs[-1][0])
    cutoff = (_parse_ts(daily_pairs[-1][0] + "T00:00:00Z" if len(daily_pairs[-1][0]) == 10 else daily_pairs[-1][0])
              - timedelta(days=WINDOW_DAYS))
    windowed = [v for d, v in daily_pairs if _to_dt(d) >= cutoff]

    percentile = _percentile(current, windowed)

    # 7d trend from the merged daily series (own+backfill), whatever is available.
    delta_7d = _delta_over_days(daily_pairs, 7)
    direction = _direction(delta_7d)

    tone = "hot" if direction == "up" else ("cold" if direction == "down" else "neutral")
    read = _h100_price_read(percentile, direction)

    provenance = None
    if splice_active:
        provenance = "history includes external tracker data until own series reaches 90d"

    return {
        "key": "h100_price",
        "title": "H100 market price",
        "value": round(current, 4),
        "unit": "$/hr",
        "value_fmt": f"${current:.2f}",
        "percentile": percentile,
        "window_days": WINDOW_DAYS,
        "direction": direction,
        "delta_7d_pct": delta_7d,
        "read": read,
        "tone": tone,
        "spark": _spark(daily_pairs),
        "provenance": provenance,
    }


def _to_dt(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _delta_over_days(daily_pairs, days):
    """% change of last value vs the value ~`days` calendar days before it
    in a chronological (date, value) list. None if not enough span."""
    if len(daily_pairs) < 2:
        return None
    last_date, last_val = daily_pairs[-1]
    target = _to_dt(last_date) - timedelta(days=days)
    # earliest point at or before target; else fall back to the earliest point available
    candidates = [(d, v) for d, v in daily_pairs if _to_dt(d) <= target]
    if candidates:
        _, base_val = candidates[-1]
    else:
        _, base_val = daily_pairs[0]
        if _to_dt(daily_pairs[0][0]) >= _to_dt(last_date):
            return None
    return _pct_change(last_val, base_val)


def _h100_price_read(percentile, direction):
    if percentile is None:
        return "Not enough history yet to rank this price."
    if percentile <= 10:
        band = "Near 90-day lows"
    elif percentile >= 90:
        band = "Near 90-day highs"
    elif percentile <= 34:
        band = "Cheap vs its 90-day history"
    elif percentile >= 66:
        band = "Rich vs its 90-day history"
    else:
        band = "Mid-range vs its 90-day history"
    if direction == "up":
        return f"{band}, trending up over the last week"
    if direction == "down":
        return f"{band}, trending down over the last week"
    return band


# ---------------------------------------------------------------------------
# availability
# ---------------------------------------------------------------------------

def _h100_offers_total(gpus_dict):
    total = 0
    any_present = False
    for k in H100_CLASSES:
        entry = (gpus_dict or {}).get(k)
        if entry and entry.get("offers") is not None:
            total += entry["offers"]
            any_present = True
    return total if any_present else None


def compute_availability(vast_hist):
    own_pairs = _downsample_daily_last(
        [(h.get("ts"), _h100_offers_total(h.get("gpus", {}))) for h in vast_hist]
    )
    if not own_pairs:
        return _null_card(
            "availability", "H100 availability", "% (7d)",
            "No H100-class offers data available yet.",
        )

    current = own_pairs[-1][1]
    n_own_days = len(own_pairs)

    if n_own_days < 8:
        # <7d of daily own history: use earliest available as baseline and say so
        base_date, base_val = own_pairs[0]
        delta_7d = _pct_change(current, base_val) if len(own_pairs) >= 2 else None
        read_suffix = f" (baseline: earliest available reading, {base_date}, only {n_own_days}d of history so far)"
    else:
        delta_7d = _delta_over_days(own_pairs, 7)
        read_suffix = ""

    direction = _direction(delta_7d)

    percentile = None
    if n_own_days >= MIN_AVAILABILITY_OWN_DAYS:
        values = [v for _, v in own_pairs]
        percentile = _percentile(current, values)

    tone = "hot" if direction == "down" else ("cold" if direction == "up" else "neutral")

    if percentile is None and n_own_days < MIN_AVAILABILITY_OWN_DAYS:
        pct_note = f" Percentile unavailable until {MIN_AVAILABILITY_OWN_DAYS}d of own history ({n_own_days}d so far)."
    else:
        pct_note = ""

    read = _availability_read(delta_7d, direction) + read_suffix + pct_note

    return {
        "key": "availability",
        "title": "H100 availability",
        "value": delta_7d,
        "unit": "% (7d)",
        "value_fmt": (f"{delta_7d:+.1f}%" if delta_7d is not None else "n/a"),
        "percentile": percentile,
        "window_days": WINDOW_DAYS,
        "direction": direction,
        "delta_7d_pct": delta_7d,
        "read": read,
        "tone": tone,
        "spark": _spark([(d, v) for d, v in own_pairs]),
        "provenance": None,
    }


def _availability_read(delta_7d, direction):
    if delta_7d is None:
        return "Not enough history yet to compute a 7-day change."
    if direction == "down":
        return "Offers thinning — capacity being absorbed"
    if direction == "up":
        return "Offers expanding — capacity loosening"
    return "Offers roughly flat over the last week"


# ---------------------------------------------------------------------------
# spot_discount
# ---------------------------------------------------------------------------

def _azure_h100_spot_ratio(line):
    """From one hyperscaler.jsonl-shaped line: cheapest US H100 spot_vm_hr /
    ondemand_gpu_hr ratio (per contract: 'spot_vm_hr/gpus / ondemand_gpu_hr').
    Picks the H100 SKU with the lowest ondemand_gpu_hr that also has a
    non-null spot_vm_hr, mirroring crosscheck's "keep lowest" convention."""
    azure = line.get("azure") or {}
    best = None
    for sku, entry in azure.items():
        if entry.get("gpu") != "H100":
            continue
        spot_vm_hr = entry.get("spot_vm_hr")
        ondemand_gpu_hr = entry.get("ondemand_gpu_hr")
        gpus_per_vm = entry.get("gpus_per_vm")
        if spot_vm_hr is None or ondemand_gpu_hr is None or not gpus_per_vm:
            continue
        spot_gpu_hr = spot_vm_hr / gpus_per_vm
        if ondemand_gpu_hr <= 0:
            continue
        ratio = spot_gpu_hr / ondemand_gpu_hr
        if best is None or ondemand_gpu_hr < best[0]:
            best = (ondemand_gpu_hr, ratio)
    return best[1] if best else None


def compute_spot_discount(hyperscaler_hist):
    pairs = _downsample_daily_last(
        [(h.get("ts"), _azure_h100_spot_ratio(h)) for h in hyperscaler_hist]
    )
    if not pairs:
        return _null_card(
            "spot_discount", "Spot discount (Azure H100)", "spot/OD",
            "No Azure H100 spot pricing available yet (spot_vm_hr null or no H100 SKU).",
        )

    current = pairs[-1][1]
    percentile = _percentile(current, [v for _, v in pairs])
    delta_7d = _delta_over_days(pairs, 7)
    direction = _direction(delta_7d)

    # tone: ratio -> 1 (spot approaches on-demand) reads as tightening (hot);
    # ratio falling / deep discount persisting reads as cold.
    if direction == "up":
        tone = "hot"
    elif direction == "down":
        tone = "cold"
    else:
        tone = "cold" if current < 0.6 else "neutral"

    read = _spot_discount_read(current, direction)

    return {
        "key": "spot_discount",
        "title": "Spot discount (Azure H100)",
        "value": round(current, 3),
        "unit": "spot/OD",
        "value_fmt": f"{current:.2f}x",
        "percentile": percentile,
        "window_days": WINDOW_DAYS,
        "direction": direction,
        "delta_7d_pct": delta_7d,
        "read": read,
        "tone": tone,
        "spark": _spark(pairs),
        "provenance": None,
    }


def _spot_discount_read(current, direction):
    if current >= 0.85:
        band = "Spot near on-demand — little idle capacity"
    elif current >= 0.6:
        band = "Moderate spot discount"
    else:
        band = "Deep discount persists — idle capacity remains"
    if direction == "up":
        return band + ", narrowing this week"
    if direction == "down":
        return band + ", widening this week"
    return band


# ---------------------------------------------------------------------------
# gen_ratio
# ---------------------------------------------------------------------------

def _blended_price(gpu_key, vast_doc, neoclouds_doc):
    """Median of available on-demand sources for `gpu_key` across the LATEST
    vast.json and neoclouds.json snapshots (contract: 'Blended = median of
    available on-demand sources for that class')."""
    vals = []
    vast_entry = (vast_doc.get("gpus") or {}).get(gpu_key)
    if vast_entry and vast_entry.get("median_dph") is not None:
        vals.append(vast_entry["median_dph"])
    for _, prices in (neoclouds_doc.get("providers") or {}).items():
        p = (prices or {}).get(gpu_key.split()[0] if " " in gpu_key else gpu_key)
        # neoclouds keys are canonical short names (H100/H200/B200); vast
        # keys can be "H100 SXM" etc. so normalize by taking the leading token.
        if p is None:
            p = (prices or {}).get(gpu_key)
        if p is not None:
            vals.append(p)
    if not vals:
        return None
    return statistics.median(vals)


def compute_gen_ratio(vast_hist, neoclouds_hist):
    vast_doc = vast_hist[-1] if vast_hist else {}
    neoclouds_doc = neoclouds_hist[-1] if neoclouds_hist else {}

    h100_now = _h100_class_median_of_medians(vast_doc.get("gpus", {}))
    if h100_now is None:
        h100_now = _blended_price("H100", vast_doc, neoclouds_doc)
    b200_now = _blended_price("B200", vast_doc, neoclouds_doc)

    if h100_now is None or b200_now is None or h100_now == 0:
        return _null_card(
            "gen_ratio", "B200/H100 (perf-adj)", "ratio",
            "Missing B200 or H100 price in the latest snapshot.",
        )

    current = (b200_now / B200_H100_PERF_COEFFICIENT) / h100_now

    # Build a daily series of this same ratio across history for percentile +
    # spark + direction + the "cold" gen_ratio tone rule (both absolute
    # generation prices fell >10% in 30d).
    series = _gen_ratio_daily_series(vast_hist, neoclouds_hist)
    if series and series[-1][1] != current:
        series.append((_date_of(vast_hist[-1].get("ts", iso_utc_now())) if vast_hist else _date_of(iso_utc_now()), current))
        series = _downsample_daily_last(series)

    percentile = _percentile(current, [v for _, v in series]) if series else None
    delta_7d = _delta_over_days(series, 7) if series else None
    direction = _direction(delta_7d)

    tone = _gen_ratio_tone(vast_hist, neoclouds_hist)
    read = _gen_ratio_read(current, direction)

    return {
        "key": "gen_ratio",
        "title": "B200/H100 (perf-adj)",
        "value": round(current, 4),
        "unit": "ratio",
        "value_fmt": f"{current:.2f}x",
        "percentile": percentile,
        "window_days": WINDOW_DAYS,
        "direction": direction,
        "delta_7d_pct": delta_7d,
        "read": read,
        "tone": tone,
        "spark": _spark(series) if series else [],
        "provenance": f"fixed conservative coefficient {B200_H100_PERF_COEFFICIENT} (MLPerf)",
    }


def _gen_ratio_daily_series(vast_hist, neoclouds_hist):
    """Pair up vast_hist lines with the neoclouds_hist line closest-in-time
    per day (both are hourly histories on the same run cadence in practice;
    we key by date and take the last-of-day for each independently, then
    intersect on shared dates)."""
    vast_by_date = dict(_downsample_daily_last(
        [(h.get("ts"), h.get("gpus", {})) for h in vast_hist]
    ))
    neo_by_date = dict(_downsample_daily_last(
        [(h.get("ts"), h.get("providers", {})) for h in neoclouds_hist]
    ))
    out = []
    for d in sorted(set(vast_by_date) & set(neo_by_date)):
        vdoc = {"gpus": vast_by_date[d]}
        ndoc = {"providers": neo_by_date[d]}
        h100 = _h100_class_median_of_medians(vdoc.get("gpus", {})) or _blended_price("H100", vdoc, ndoc)
        b200 = _blended_price("B200", vdoc, ndoc)
        if h100 and b200 and h100 != 0:
            out.append((d, (b200 / B200_H100_PERF_COEFFICIENT) / h100))
    return out


def _gen_ratio_tone(vast_hist, neoclouds_hist):
    """neutral unless BOTH generations' absolute prices fell >10% in 30d ->
    cold (per contract)."""
    h100_series = _downsample_daily_last(
        [(h.get("ts"), _h100_class_median_of_medians(h.get("gpus", {}))) for h in vast_hist]
    )
    b200_series = []
    for h in vast_hist:
        b = (h.get("gpus", {}) or {}).get("B200")
        b200_series.append((h.get("ts"), b.get("median_dph") if b else None))
    b200_series = _downsample_daily_last(b200_series)

    h100_delta = _delta_over_days(h100_series, 30) if len(h100_series) >= 2 else None
    b200_delta = _delta_over_days(b200_series, 30) if len(b200_series) >= 2 else None

    if h100_delta is not None and b200_delta is not None and h100_delta < -10 and b200_delta < -10:
        return "cold"
    return "neutral"


def _gen_ratio_read(current, direction):
    if current <= 1.0:
        band = "Blackwell already at or below H100 compute-price parity"
    elif current <= 1.2:
        band = "Blackwell nearing compute-price parity"
    else:
        band = "Blackwell still carries a compute-price premium"
    if direction == "up":
        return band + ", premium widening"
    if direction == "down":
        return band + ", premium narrowing"
    return band


# ---------------------------------------------------------------------------
# token_growth
# ---------------------------------------------------------------------------

def _ma7_series(daily_values):
    """[v0, v1, ...] chronological daily values -> list of trailing-7d
    simple moving averages, same length, None for the first 6 (insufficient
    window)."""
    out = []
    for i in range(len(daily_values)):
        if i < 6:
            out.append(None)
            continue
        window = daily_values[i - 6:i + 1]
        out.append(statistics.mean(window))
    return out


def compute_token_growth(openrouter_tokens_hist):
    daily_pairs = sorted(
        {(h.get("date") or _date_of(h.get("ts", ""))): h.get("total_b_tokens")
         for h in openrouter_tokens_hist if h.get("total_b_tokens") is not None}.items()
    )
    if len(daily_pairs) < 8:
        return _null_card(
            "token_growth", "Token volume growth", "% (30d)",
            "Not enough OpenRouter token history yet (need >=8d for a 7-day average).",
        )

    dates = [d for d, _ in daily_pairs]
    values = [v for _, v in daily_pairs]
    ma7 = _ma7_series(values)

    ma7_pairs = [(dates[i], ma7[i]) for i in range(len(dates)) if ma7[i] is not None]
    if len(ma7_pairs) < 2:
        return _null_card(
            "token_growth", "Token volume growth", "% (30d)",
            "Not enough 7dMA history yet to compute 30d growth.",
        )

    latest_date, latest_ma7 = ma7_pairs[-1]
    target = _to_dt(latest_date) - timedelta(days=30)
    earlier_candidates = [(d, v) for d, v in ma7_pairs if _to_dt(d) <= target]
    if earlier_candidates:
        _, earlier_ma7 = earlier_candidates[-1]
    else:
        # <30d of 7dMA history: fall back to earliest available 7dMA point
        _, earlier_ma7 = ma7_pairs[0]

    growth_pct = _pct_change(latest_ma7, earlier_ma7)
    if growth_pct is None:
        return _null_card(
            "token_growth", "Token volume growth", "% (30d)",
            "Could not compute 30d growth (zero or missing baseline).",
        )

    # Percentile over the growth series across the 90d window (contract:
    # "this one HAS deep history" -> build the full growth-series history).
    growth_series = []
    for i in range(len(ma7_pairs)):
        d, v = ma7_pairs[i]
        t = _to_dt(d) - timedelta(days=30)
        cands = [(dd, vv) for dd, vv in ma7_pairs[:i + 1] if _to_dt(dd) <= t]
        if cands:
            _, base = cands[-1]
            g = _pct_change(v, base)
            if g is not None:
                growth_series.append((d, g))

    windowed_growth = [(d, g) for d, g in growth_series if _to_dt(d) >= _to_dt(latest_date) - timedelta(days=WINDOW_DAYS)]
    percentile = _percentile(growth_pct, [g for _, g in windowed_growth])

    delta_7d = _delta_over_days(growth_series, 7) if len(growth_series) >= 2 else None
    direction = _direction(delta_7d if delta_7d is not None else 0.0, deadband=DIRECTION_DEADBAND_PCT) if delta_7d is not None else _direction(growth_pct)
    tone = "hot" if growth_pct > DIRECTION_DEADBAND_PCT else ("cold" if growth_pct < -DIRECTION_DEADBAND_PCT else "neutral")

    read = _token_growth_read(growth_pct, direction)

    return {
        "key": "token_growth",
        "title": "Token volume growth",
        "value": round(growth_pct, 2),
        "unit": "% (30d)",
        "value_fmt": f"{growth_pct:+.0f}%",
        "percentile": percentile,
        "window_days": WINDOW_DAYS,
        "direction": direction,
        "delta_7d_pct": delta_7d,
        "read": read,
        "tone": tone,
        "spark": _spark(daily_pairs),
        "provenance": None,
    }


def _token_growth_read(growth_pct, direction):
    if growth_pct >= 20:
        band = "Demand still compounding — no deceleration"
    elif growth_pct > 0:
        band = "Token volume growing"
    elif growth_pct > -10:
        band = "Token volume roughly flat"
    else:
        band = "Token volume contracting"
    if direction == "up" and growth_pct < 20:
        return band + ", accelerating"
    if direction == "down" and growth_pct > 0:
        return band + ", decelerating"
    return band


# ---------------------------------------------------------------------------
# Shared null-card helper
# ---------------------------------------------------------------------------

def _null_card(key, title, unit, read):
    return {
        "key": key,
        "title": title,
        "value": None,
        "unit": unit,
        "value_fmt": "n/a",
        "percentile": None,
        "window_days": WINDOW_DAYS,
        "direction": "flat",
        "delta_7d_pct": None,
        "read": read,
        "tone": "neutral",
        "spark": [],
        "provenance": None,
    }


# ---------------------------------------------------------------------------
# collect / write / main
# ---------------------------------------------------------------------------

def collect():
    errors = []

    vast_hist = read_history("vast")
    vast_backfill_hist = read_history("vast_backfill")
    neoclouds_hist = read_history("neoclouds")
    hyperscaler_hist = read_history("hyperscaler")
    openrouter_tokens_hist = read_history("openrouter_tokens")
    composite_doc = _read_latest_json("composite")

    cards = []
    for name, fn in (
        ("h100_price", lambda: compute_h100_price(vast_hist, vast_backfill_hist)),
        ("availability", lambda: compute_availability(vast_hist)),
        ("spot_discount", lambda: compute_spot_discount(hyperscaler_hist)),
        ("gen_ratio", lambda: compute_gen_ratio(vast_hist, neoclouds_hist)),
        ("token_growth", lambda: compute_token_growth(openrouter_tokens_hist)),
    ):
        try:
            cards.append(fn())
        except Exception as e:  # noqa: BLE001 - a card must never crash the run
            errors.append({"card": name, "error": repr(e)})
            title_map = {
                "h100_price": ("H100 market price", "$/hr"),
                "availability": ("H100 availability", "% (7d)"),
                "spot_discount": ("Spot discount (Azure H100)", "spot/OD"),
                "gen_ratio": ("B200/H100 (perf-adj)", "ratio"),
                "token_growth": ("Token volume growth", "% (30d)"),
            }
            title, unit = title_map[name]
            cards.append(_null_card(name, title, unit, f"Internal error computing this card: {e}"))

    composite_summary = {
        "index": composite_doc.get("index"),
        "label": composite_doc.get("label"),
    } if composite_doc else {"index": None, "label": None}

    return {
        "asof": iso_utc_now(),
        "cards": cards,
        "composite": composite_summary,
        "errors": errors,
    }


def write(payload):
    atomic_write_json(latest_path("signals"), payload)


def main():
    payload = collect()
    write(payload)
    n_null = sum(1 for c in payload["cards"] if c.get("value") is None)
    print(f"[signals] wrote {latest_path('signals')} "
          f"({len(payload['cards'])} cards, {n_null} null, {len(payload['errors'])} errors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
