#!/usr/bin/env python3
"""Shared helpers for Watts & Wafers collectors.

Stdlib-only (urllib, json, os, time, datetime). Every collector imports this
module for: HTTP fetch with retries, atomic JSON writes, and history-file
append + rotation per docs/DATA_CONTRACT.md.
"""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

UA = "WattsAndWafers/1.0 (+github.com/jingchaodev/watts-and-wafers)"

# collectors/ -> repo root -> data/
HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
DATA_LATEST = os.path.join(REPO_ROOT, "data", "latest")
DATA_HISTORY = os.path.join(REPO_ROOT, "data", "history")

HISTORY_MAX_LINES = 20000
HISTORY_DROP_FRACTION = 0.25


def iso_utc_now():
    """Current UTC time as ISO-8601 with Z suffix, second precision."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch_url(url, method="GET", body=None, headers=None, timeout=25, retries=2):
    """GET/POST a URL with our UA, retrying transient failures.

    body, if given, is a dict that gets JSON-encoded (Content-Type set
    automatically). Returns the decoded text body. Raises on final failure —
    callers are expected to catch and record into their own errors[].
    """
    h = {"User-Agent": UA, **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    last_err = None
    attempts = max(1, retries + 1)
    for attempt in range(attempts):
        req = urllib.request.Request(url, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:  # noqa: BLE001 - want to retry any transient failure
            last_err = e
            if attempt < attempts - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last_err


def atomic_write_json(path, payload):
    """Write JSON atomically: write to a tmp file in the same dir, then os.replace."""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def latest_path(name):
    """data/latest/<name>.json"""
    return os.path.join(DATA_LATEST, f"{name}.json")


def history_path(name):
    """data/history/<name>.jsonl"""
    return os.path.join(DATA_HISTORY, f"{name}.jsonl")


def append_history(name, line_dict):
    """Append one compact JSON line to data/history/<name>.jsonl, then rotate
    if the file exceeds HISTORY_MAX_LINES: drop the oldest 25%.
    """
    path = history_path(name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(line_dict, ensure_ascii=False) + "\n")
    _rotate_history(path)


def _rotate_history(path):
    try:
        with open(path) as f:
            lines = f.read().splitlines()
    except FileNotFoundError:
        return
    if len(lines) <= HISTORY_MAX_LINES:
        return
    drop = int(len(lines) * HISTORY_DROP_FRACTION)
    kept = lines[drop:]
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write("\n".join(kept) + ("\n" if kept else ""))
    os.replace(tmp, path)


def read_history(name, limit=None):
    """Read data/history/<name>.jsonl into a list of dicts (oldest first).
    Returns [] if the file doesn't exist or lines fail to parse.
    """
    path = history_path(name)
    out = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        return []
    if limit:
        out = out[-limit:]
    return out
