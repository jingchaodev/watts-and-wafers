#!/usr/bin/env python3
"""OpenRouter collector — model cost / Pareto ($/M tokens), daily.

GET https://openrouter.ai/api/v1/models (no auth). Pricing in the raw API is
USD per TOKEN as a numeric string (e.g. "0.000015"); we convert to USD per
MILLION tokens. Writes data/latest/openrouter.json per docs/DATA_CONTRACT.md.

tokens_daily: OpenRouter has no public "daily tokens routed" endpoint as of
this writing. If OPENROUTER_API_KEY is set we attempt an authenticated call
via fetch_tokens_daily(); today that's a documented TODO stub returning None
(see function docstring) so the field degrades to null with no error, per
contract.
"""
import os
import statistics
import sys

import json

from common import atomic_write_json, append_history, fetch_url, history_path, iso_utc_now, latest_path

MODELS_URL = "https://openrouter.ai/api/v1/models"
MAX_MODELS = 150
FRONTIER_N = 15


def fetch_models(timeout=25, retries=2):
    return fetch_url(MODELS_URL, timeout=timeout, retries=retries)


def _price_per_m(pricing, key):
    """Convert an OpenRouter pricing field (USD/token, string) to USD/M tokens.
    Returns None for missing/non-numeric/negative (e.g. "-1" = N/A) values.
    """
    raw = (pricing or {}).get(key)
    if raw is None:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    if v < 0:
        return None
    return round(v * 1_000_000, 6)


def parse_models(raw_json_text):
    """Pure parse: raw /models response text -> contract's openrouter.json dict
    (minus asof, which the caller stamps).
    """
    import json

    doc = json.loads(raw_json_text)
    raw_models = doc.get("data") or []

    parsed = []
    for m in raw_models:
        pricing = m.get("pricing") or {}
        prompt_usd_per_m = _price_per_m(pricing, "prompt")
        completion_usd_per_m = _price_per_m(pricing, "completion")
        if completion_usd_per_m is None:
            continue  # unpriced (e.g. auto-router) — excluded from the cost tape
        parsed.append({
            "id": m.get("id"),
            "name": m.get("name") or m.get("id"),
            "prompt_usd_per_m": prompt_usd_per_m,
            "completion_usd_per_m": completion_usd_per_m,
            "context": m.get("context_length"),
        })

    parsed.sort(key=lambda x: x["completion_usd_per_m"], reverse=True)
    capped = parsed[:MAX_MODELS]

    # Frontier = median of per-lab flagship completion prices. Taking the N
    # priciest models overall skews to legacy relics still listed at $600/M
    # (o1-pro class); per-lab max with an outlier cap tracks what flagship
    # intelligence actually costs, and is stable when a relic gets delisted.
    FRONTIER_OUTLIER_CAP = 100.0  # USD/M — above this = legacy list price, not frontier
    per_lab_flagship = {}
    for m in parsed:
        price = m["completion_usd_per_m"]
        if price is None or price <= 0 or price > FRONTIER_OUTLIER_CAP:
            continue  # free-tier listings and legacy relics both distort the flagship read
        lab = (m["id"] or "").split("/")[0]
        if not lab:
            continue
        if lab not in per_lab_flagship or price > per_lab_flagship[lab]:
            per_lab_flagship[lab] = price
    flagships = sorted(per_lab_flagship.values(), reverse=True)[:FRONTIER_N]
    frontier_median = round(statistics.median(flagships), 4) if flagships else None

    return {
        "n_models": len(raw_models),
        "models": capped,
        "frontier_median_completion_usd_per_m": frontier_median,
    }


def parse_rankings_daily(raw_json_text):
    """Pure parse: /api/v1/datasets/rankings-daily response -> {date: {slug: tokens}}."""
    doc = json.loads(raw_json_text)
    by_day = {}
    for r in doc.get("data") or []:
        try:
            by_day.setdefault(r["date"], {})[r["model_permaslug"]] = int(r["total_tokens"])
        except (KeyError, TypeError, ValueError):
            continue
    return by_day


def _day_summary(day, models):
    total = sum(models.values())
    top = sorted(models.items(), key=lambda kv: -kv[1])[:10]
    return {
        "ts": f"{day}T00:00:00Z",
        "date": day,
        "total_b_tokens": round(total / 1e9, 2),
        "top_models": [{"slug": s, "b_tokens": round(v / 1e9, 2)} for s, v in top],
    }


def fetch_tokens_daily():
    """Official dataset endpoint (added 2026-07-17, verified live): per-model
    daily token totals since 2025-01-01. Requires OPENROUTER_API_KEY. Fetches
    the last few completed days, appends any missing dates to
    data/history/openrouter_tokens.jsonl, and returns the latest day summary.
    """
    import datetime as _dt

    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        return None
    end = _dt.date.today() - _dt.timedelta(days=1)
    start = end - _dt.timedelta(days=4)
    raw = fetch_url(
        f"https://openrouter.ai/api/v1/datasets/rankings-daily?start_date={start}&end_date={end}",
        headers={"Authorization": f"Bearer {key}"},
    )
    by_day = parse_rankings_daily(raw)
    if not by_day:
        return None

    hist = history_path("openrouter_tokens")
    have = set()
    if os.path.exists(hist):
        with open(hist) as f:
            for line in f:
                try:
                    have.add(json.loads(line)["date"])
                except (ValueError, KeyError):
                    continue
    new_days = [d for d in sorted(by_day) if d not in have]
    if new_days:
        with open(hist, "a") as f:
            for d in new_days:
                f.write(json.dumps(_day_summary(d, by_day[d])) + "\n")
    latest = max(by_day)
    return _day_summary(latest, by_day[latest])


def collect():
    errors = []
    result = {"n_models": 0, "models": [], "frontier_median_completion_usd_per_m": None}
    try:
        raw = fetch_models()
        result = parse_models(raw)
    except Exception as e:  # noqa: BLE001
        errors.append({"source": "openrouter_models", "error": repr(e)})
        print(f"[openrouter] models ERROR: {e}", file=sys.stderr)

    tokens_daily = None
    if os.environ.get("OPENROUTER_API_KEY"):
        try:
            tokens_daily = fetch_tokens_daily()
        except Exception as e:  # noqa: BLE001
            errors.append({"source": "openrouter_tokens_daily", "error": repr(e)})
            print(f"[openrouter] tokens_daily ERROR: {e}", file=sys.stderr)

    return {
        "asof": iso_utc_now(),
        "n_models": result["n_models"],
        "models": result["models"],
        "frontier_median_completion_usd_per_m": result["frontier_median_completion_usd_per_m"],
        "tokens_daily": tokens_daily,
        "errors": errors,
    }


def write(payload):
    atomic_write_json(latest_path("openrouter"), payload)
    append_history("openrouter", {
        "ts": payload["asof"],
        "frontier_median_completion_usd_per_m": payload.get("frontier_median_completion_usd_per_m"),
        "n_models": payload.get("n_models"),
    })


def main():
    payload = collect()
    write(payload)
    n_err = len(payload["errors"])
    print(f"[openrouter] wrote {latest_path('openrouter')} "
          f"(n_models={payload['n_models']}, {n_err} errors)")
    return 0 if payload["n_models"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
