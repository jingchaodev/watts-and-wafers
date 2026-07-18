#!/usr/bin/env python3
"""Signal-events collector (every run, after signals.py) — detects notable
crossings in the just-computed signals.json cards and composite label, per
docs/DATA_CONTRACT.md's `signal_events.json` section.

Event kinds:
  - percentile_cross: a card's percentile enters <=P10 or >=P90 (fire once
    per crossing, i.e. only on the transition INTO the extreme band, not on
    every run while it stays there).
  - label_flip: the composite label differs from the previous run's label.
  - shock: availability's 7d %change has |value| > 30%.

Dedup: a 7-day cooldown per (signal, direction, kind) tuple, using
data/history/signal_events.jsonl as the durable state (we scan it for the
most recent prior event matching the same tuple and suppress a new one if
it's within 7 days).

Writes data/latest/signal_events.json (most recent 20 events) and appends
each NEW event as one line to data/history/signal_events.jsonl.
"""
import sys
from datetime import datetime, timedelta, timezone

from common import append_history, atomic_write_json, iso_utc_now, latest_path, read_history

COOLDOWN_DAYS = 7
LATEST_EVENTS_CAP = 20
PERCENTILE_LOW = 10
PERCENTILE_HIGH = 90
AVAILABILITY_SHOCK_PCT = 30.0


def _parse_date(date_str):
    return datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _today(asof):
    return asof[:10]


def _band(percentile):
    if percentile is None:
        return None
    if percentile <= PERCENTILE_LOW:
        return "low"
    if percentile >= PERCENTILE_HIGH:
        return "high"
    return None


def detect_percentile_cross_events(signals_payload, prev_cards_by_key, today):
    """Compare each card's current percentile band (low/high/mid) against
    the previous run's band for that same card. Fires only on the
    transition INTO low or high (i.e. previous band != current extreme
    band)."""
    events = []
    for card in signals_payload.get("cards", []):
        key = card.get("key")
        percentile = card.get("percentile")
        cur_band = _band(percentile)
        if cur_band is None:
            continue
        prev_card = prev_cards_by_key.get(key) or {}
        prev_band = _band(prev_card.get("percentile"))
        if prev_band == cur_band:
            continue  # already in this band last run -> not a new crossing
        direction = "up" if cur_band == "high" else "down"
        p_label = f"P{percentile}"
        detail = f"{card.get('title', key)} entered {p_label} ({card.get('window_days', 90)}d)"
        events.append({
            "date": today,
            "signal": key,
            "kind": "percentile_cross",
            "direction": direction,
            "detail": detail,
        })
    return events


def detect_label_flip_event(signals_payload, prev_composite, today):
    label = (signals_payload.get("composite") or {}).get("label")
    prev_label = (prev_composite or {}).get("label")
    if label is None or prev_label is None or label == prev_label:
        return []
    # direction: rank labels loosely by tightening-ness for the event's
    # direction field; fall back to "up" if unranked.
    order = ["GLUT", "SOFTENING", "NEUTRAL", "TIGHTENING", "SURGING"]
    try:
        direction = "up" if order.index(label) > order.index(prev_label) else "down"
    except ValueError:
        direction = "up"
    return [{
        "date": today,
        "signal": "composite",
        "kind": "label_flip",
        "direction": direction,
        "detail": f"Composite label {prev_label} -> {label}",
    }]


def detect_shock_events(signals_payload, today):
    events = []
    for card in signals_payload.get("cards", []):
        if card.get("key") != "availability":
            continue
        delta = card.get("delta_7d_pct")
        if delta is None or abs(delta) <= AVAILABILITY_SHOCK_PCT:
            continue
        direction = "down" if delta < 0 else "up"
        events.append({
            "date": today,
            "signal": "availability",
            "kind": "shock",
            "direction": direction,
            "detail": f"H100 offers 7d {delta:+.0f}%",
        })
    return events


def _last_event_date_for(history_events, signal, kind, direction):
    """Most recent (max date) prior event matching this exact
    (signal, kind, direction) tuple, or None."""
    matches = [
        e for e in history_events
        if e.get("signal") == signal and e.get("kind") == kind and e.get("direction") == direction
    ]
    if not matches:
        return None
    return max(e.get("date") for e in matches if e.get("date"))


def apply_cooldown(candidate_events, history_events, today):
    """Drop any candidate event whose (signal, kind, direction) tuple fired
    within the last COOLDOWN_DAYS days (per the history file's state)."""
    today_dt = _parse_date(today)
    kept = []
    for ev in candidate_events:
        last_date = _last_event_date_for(
            history_events, ev["signal"], ev["kind"], ev["direction"]
        )
        if last_date is not None:
            try:
                days_since = (today_dt - _parse_date(last_date)).days
            except ValueError:
                days_since = COOLDOWN_DAYS + 1
            if days_since < COOLDOWN_DAYS:
                continue
        kept.append(ev)
    return kept


def compute_events(signals_payload, prev_signals_payload, history_events):
    """Pure: current signals.json payload + previous run's signals.json
    payload (for percentile/label diffing) + prior signal_events history ->
    list of NEW event dicts (post-cooldown)."""
    today = _today(signals_payload.get("asof") or iso_utc_now())

    prev_cards_by_key = {
        c.get("key"): c for c in (prev_signals_payload or {}).get("cards", [])
    }
    prev_composite = (prev_signals_payload or {}).get("composite")

    candidates = []
    candidates += detect_percentile_cross_events(signals_payload, prev_cards_by_key, today)
    candidates += detect_label_flip_event(signals_payload, prev_composite, today)
    candidates += detect_shock_events(signals_payload, today)

    return apply_cooldown(candidates, history_events, today)


def _read_current_signals():
    """Read the data/latest/signals.json that signals.py just wrote this run
    (signal_events always runs immediately after signals in run.py's
    groups)."""
    import json
    try:
        with open(latest_path("signals")) as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}


STATE_HISTORY_NAME = "signal_events_state"


def _load_prev_state():
    """This module keeps its own tiny prev-cards snapshot (separate from the
    live data/latest/signals.json, so a re-run or the file being overwritten
    doesn't destroy the 'previous' reference needed for percentile_cross /
    label_flip diffing). Stored as a single-line jsonl (only ever one line,
    rewritten each run) at data/history/signal_events_state.jsonl."""
    lines = read_history(STATE_HISTORY_NAME)
    return lines[-1] if lines else {}


def _save_prev_state(signals_payload):
    """Overwrite the tiny state file with the just-seen signals_payload
    (cards + composite only) so next run can diff against it. Not an
    append-forever log: we truncate to a single line each time via direct
    write (append_history would grow unboundedly at every-run cadence)."""
    import json
    from common import DATA_HISTORY
    import os
    path = os.path.join(DATA_HISTORY, f"{STATE_HISTORY_NAME}.jsonl")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    snapshot = {
        "cards": [{"key": c.get("key"), "percentile": c.get("percentile")} for c in signals_payload.get("cards", [])],
        "composite": signals_payload.get("composite"),
    }
    with open(tmp, "w") as f:
        f.write(json.dumps(snapshot, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def collect():
    signals_payload = _read_current_signals()  # the file signals.py just wrote (this run)
    prev_state = _load_prev_state()  # snapshot saved at the END of the previous run
    history_events = read_history("signal_events")

    new_events = compute_events(signals_payload, prev_state, history_events)

    latest_events = (list(reversed(new_events)) + list(reversed(history_events)))[:LATEST_EVENTS_CAP]
    # history_events is chronological (oldest first) from read_history; we
    # want most-recent-first for the `latest` list per the sample shape.

    errors = []
    if not signals_payload:
        errors.append({"source": "signals", "error": "latest/signals.json missing or unreadable"})

    payload = {
        "asof": iso_utc_now(),
        "events": latest_events,
        "errors": errors,
    }

    return payload, new_events, signals_payload


def write(payload, new_events, signals_payload):
    atomic_write_json(latest_path("signal_events"), payload)
    for ev in new_events:
        append_history("signal_events", ev)
    if signals_payload:
        _save_prev_state(signals_payload)


def main():
    payload, new_events, signals_payload = collect()
    write(payload, new_events, signals_payload)
    print(f"[signal_events] wrote {latest_path('signal_events')} "
          f"({len(new_events)} new events, {len(payload['events'])} in latest)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
