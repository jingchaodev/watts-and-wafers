#!/usr/bin/env python3
"""One-shot backfill of Vast.ai median price + offer counts from
github.com/cherielilili/gpu-pricing-tracker (same public bundles API and the
same per-GPU normalization as our collectors/vast.py — verified 2026-07-17).

Writes data/history/vast_backfill.jsonl in vast.jsonl's schema, one line per
day, only from rows the tracker fetched live off console.vast.ai on or after
2026-05-08 (its earlier rows came from an aggregator re-import we don't trust;
see data/history/BACKFILL_PROVENANCE.md).
"""
import csv
import io
import json
import os
import urllib.request
from collections import defaultdict

CSV_URL = "https://raw.githubusercontent.com/cherielilili/gpu-pricing-tracker/main/data/observations.csv"
OUT = os.path.join(os.path.dirname(__file__), "..", "data", "history", "vast_backfill.jsonl")
MIN_DATE = "2026-05-08"

# tracker's normalized names -> our vast.jsonl class names
NAME_MAP = {
    "H100_SXM": "H100 SXM",
    "H100_NVL": "H100 NVL",
    "H200": "H200",
    "B200": "B200",
    "A100_SXM_80GB": "A100 SXM4",
    "RTX_4090": "RTX 4090",
    "MI300X": "MI300X",
}


def main():
    raw = urllib.request.urlopen(
        urllib.request.Request(CSV_URL, headers={"User-Agent": "WattsAndWafers/1.0"}), timeout=30
    ).read().decode("utf-8")
    by_day = defaultdict(dict)
    for row in csv.DictReader(io.StringIO(raw)):
        if row["provider"] != "vast.ai" or row["rental_type"] != "on_demand":
            continue
        if "console.vast.ai" not in (row.get("source_url") or ""):
            continue
        if row["date"] < MIN_DATE:
            continue
        gpu = NAME_MAP.get(row["gpu_model"])
        if not gpu:
            continue
        try:
            median = float(row["price_median_usd"])
            offers = int(row["n_offers"])
        except (ValueError, TypeError):
            continue
        # one observation per (day, gpu); keep the last fetched
        by_day[row["date"]][gpu] = {"offers": offers, "median_dph": round(median, 4)}

    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        for day in sorted(by_day):
            f.write(json.dumps({
                "ts": f"{day}T12:00:00Z",
                "gpus": by_day[day],
                "source": "github:cherielilili/gpu-pricing-tracker",
            }) + "\n")
    os.replace(tmp, OUT)
    print(f"wrote {len(by_day)} days -> {OUT}")


if __name__ == "__main__":
    main()
