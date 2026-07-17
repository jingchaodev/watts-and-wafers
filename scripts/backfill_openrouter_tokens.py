#!/usr/bin/env python3
"""One-shot backfill of daily token volumes from OpenRouter's official
/api/v1/datasets/rankings-daily dataset (starts 2025-01-01, needs API key).

Writes data/history/openrouter_tokens.jsonl — one line per day:
  {"ts": "...T00:00:00Z", "date": "YYYY-MM-DD", "total_b_tokens": float,
   "top_models": [{"slug": str, "b_tokens": float} x 10]}
Idempotent: rewrites the whole file sorted by date.
"""
import json
import os
import time
import urllib.request
from collections import defaultdict
from datetime import date, timedelta

OUT = os.path.join(os.path.dirname(__file__), "..", "data", "history", "openrouter_tokens.jsonl")
KEY = os.environ.get("OPENROUTER_API_KEY")
if not KEY:
    raise SystemExit("OPENROUTER_API_KEY not set")


def fetch_window(start, end):
    url = f"https://openrouter.ai/api/v1/datasets/rankings-daily?start_date={start}&end_date={end}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {KEY}", "User-Agent": "WattsAndWafers/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())["data"]


def main():
    by_day = defaultdict(dict)  # date -> slug -> tokens
    start = date(2025, 1, 1)
    today = date.today()
    cur = start
    while cur < today:
        end = min(cur + timedelta(days=89), today - timedelta(days=1))
        rows = fetch_window(cur.isoformat(), end.isoformat())
        for r in rows:
            by_day[r["date"]][r["model_permaslug"]] = int(r["total_tokens"])
        print(f"{cur} → {end}: {len(rows)} rows")
        cur = end + timedelta(days=1)
        time.sleep(2.5)

    tmp = OUT + ".tmp"
    with open(tmp, "w") as f:
        for day in sorted(by_day):
            models = by_day[day]
            total = sum(models.values())
            top = sorted(models.items(), key=lambda kv: -kv[1])[:10]
            f.write(json.dumps({
                "ts": f"{day}T00:00:00Z",
                "date": day,
                "total_b_tokens": round(total / 1e9, 2),
                "top_models": [{"slug": s, "b_tokens": round(v / 1e9, 2)} for s, v in top],
            }) + "\n")
    os.replace(tmp, OUT)
    print(f"wrote {len(by_day)} days -> {OUT}")


if __name__ == "__main__":
    main()
