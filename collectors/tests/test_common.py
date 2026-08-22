"""Tests for common.py — the shared I/O layer every collector depends on.

Covers: timestamp formatting, HTTP fetch with retries, atomic JSON writes,
history append + rotation, and history/latest reads. All file I/O is
redirected to tmp_path; nothing touches the repo's real data/ directory.
"""
import json
import os
import re
import urllib.error
from datetime import datetime, timezone
from email.message import Message

import pytest

import common


# ---------------------------------------------------------------------------
# iso_utc_now
# ---------------------------------------------------------------------------

def test_iso_utc_now_format():
    ts = common.iso_utc_now()
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ts)
    # Round-trips as UTC (Z suffix, no offset drift)
    parsed = datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    assert parsed.tzinfo == timezone.utc


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def test_latest_path_layout():
    assert common.latest_path("vast") == os.path.join(common.DATA_LATEST, "vast.json")


def test_history_path_layout():
    assert common.history_path("vast") == os.path.join(common.DATA_HISTORY, "vast.jsonl")


# ---------------------------------------------------------------------------
# fetch_url
# ---------------------------------------------------------------------------

class FakeResp:
    def __init__(self, body):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def _patch_urlopen(monkeypatch, fn):
    monkeypatch.setattr(common.urllib.request, "urlopen", fn)
    monkeypatch.setattr(common.time, "sleep", lambda s: None)


def test_fetch_url_get_success(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=25):
        seen["url"] = req.full_url
        seen["method"] = req.get_method()
        seen["ua"] = req.get_header("User-agent")
        seen["timeout"] = timeout
        return FakeResp(b'{"ok": true}')

    _patch_urlopen(monkeypatch, fake_urlopen)
    body = common.fetch_url("https://example.test/api")
    assert body == '{"ok": true}'
    assert seen["url"] == "https://example.test/api"
    assert seen["method"] == "GET"
    assert seen["ua"] == common.UA
    assert seen["timeout"] == 25


def test_fetch_url_post_json_body(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=25):
        seen["data"] = req.data
        seen["ctype"] = req.get_header("Content-type")
        seen["method"] = req.get_method()
        return FakeResp(b"{}")

    _patch_urlopen(monkeypatch, fake_urlopen)
    common.fetch_url("https://example.test/api", method="POST", body={"a": 1})
    assert json.loads(seen["data"]) == {"a": 1}
    assert seen["method"] == "POST"
    assert seen["ctype"] == "application/json"


def test_fetch_url_custom_headers_merge(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=25):
        seen["x"] = req.headers.get("X-custom")
        seen["ua"] = req.get_header("User-agent")
        return FakeResp(b"")

    _patch_urlopen(monkeypatch, fake_urlopen)
    common.fetch_url("https://example.test", headers={"X-Custom": "yes"})
    assert seen["x"] == "yes"
    assert seen["ua"] == common.UA


def test_fetch_url_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=25):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.URLError("transient")
        return FakeResp(b"ok")

    _patch_urlopen(monkeypatch, fake_urlopen)
    assert common.fetch_url("https://example.test") == "ok"
    assert calls["n"] == 2  # 1 failed attempt + 1 retry


def test_fetch_url_gives_up_after_retries(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=25):
        calls["n"] += 1
        raise urllib.error.URLError("always down")

    _patch_urlopen(monkeypatch, fake_urlopen)
    with pytest.raises(urllib.error.URLError):
        common.fetch_url("https://example.test")  # default retries=2 -> 3 attempts
    assert calls["n"] == 3


def test_fetch_url_zero_retries_single_attempt(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=25):
        calls["n"] += 1
        raise urllib.error.URLError("down")

    _patch_urlopen(monkeypatch, fake_urlopen)
    with pytest.raises(urllib.error.URLError):
        common.fetch_url("https://example.test", retries=0)
    assert calls["n"] == 1


def test_fetch_url_http_error_is_retried(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=25):
        calls["n"] += 1
        raise urllib.error.HTTPError(req.full_url, 503, "unavailable", Message(), None)

    _patch_urlopen(monkeypatch, fake_urlopen)
    with pytest.raises(urllib.error.HTTPError):
        common.fetch_url("https://example.test")
    assert calls["n"] == 3


def test_fetch_url_decodes_with_replace(monkeypatch):
    def fake_urlopen(req, timeout=25):
        return FakeResp(b"\xff\xfe not utf8")

    _patch_urlopen(monkeypatch, fake_urlopen)
    body = common.fetch_url("https://example.test")
    assert "\ufffd" in body  # replacement char, not a crash


# ---------------------------------------------------------------------------
# atomic_write_json
# ---------------------------------------------------------------------------

def test_atomic_write_json_roundtrip(tmp_path):
    p = tmp_path / "sub" / "latest.json"  # parent dir does not exist yet
    common.atomic_write_json(str(p), {"a": 1, "b": [1, 2]})
    assert json.loads(p.read_text(encoding="utf-8")) == {"a": 1, "b": [1, 2]}


def test_atomic_write_json_trailing_newline(tmp_path):
    p = tmp_path / "out.json"
    common.atomic_write_json(str(p), {"a": 1})
    raw = p.read_text(encoding="utf-8")
    assert raw.endswith("\n")


def test_atomic_write_json_no_tmp_leftover(tmp_path):
    p = tmp_path / "out.json"
    common.atomic_write_json(str(p), {"a": 1})
    assert not (tmp_path / "out.json.tmp").exists()


def test_atomic_write_json_utf8_payload(tmp_path):
    # ensure_ascii=False writes non-ASCII literally; must survive as UTF-8
    p = tmp_path / "out.json"
    common.atomic_write_json(str(p), {"note": "TrendForce 现货 ¥ 涨"})
    assert p.read_text(encoding="utf-8") == '{\n  "note": "TrendForce 现货 ¥ 涨"\n}\n'


def test_atomic_write_json_overwrites(tmp_path):
    p = tmp_path / "out.json"
    common.atomic_write_json(str(p), {"v": 1})
    common.atomic_write_json(str(p), {"v": 2})
    assert json.loads(p.read_text(encoding="utf-8")) == {"v": 2}


# ---------------------------------------------------------------------------
# append_history / _rotate_history
# ---------------------------------------------------------------------------

@pytest.fixture
def history_dir(tmp_path, monkeypatch):
    d = tmp_path / "history"
    d.mkdir()
    monkeypatch.setattr(common, "DATA_HISTORY", str(d))
    return d


def test_append_history_creates_dirs_and_appends(history_dir):
    common.append_history("vast", {"ts": "t1", "gpus": 1})
    common.append_history("vast", {"ts": "t2", "gpus": 2})
    lines = (history_dir / "vast.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"ts": "t1", "gpus": 1}
    assert json.loads(lines[1]) == {"ts": "t2", "gpus": 2}


def test_append_history_compact_lines(history_dir):
    # History lines are compact JSON (no indent), matching DATA_CONTRACT
    common.append_history("vast", {"a": 1})
    raw = (history_dir / "vast.jsonl").read_text(encoding="utf-8")
    assert raw == '{"a": 1}\n'


def test_append_history_rotates_over_limit(history_dir, monkeypatch):
    monkeypatch.setattr(common, "HISTORY_MAX_LINES", 6)
    monkeypatch.setattr(common, "HISTORY_DROP_FRACTION", 0.25)
    for i in range(8):
        common.append_history("vast", {"i": i})
    lines = (history_dir / "vast.jsonl").read_text(encoding="utf-8").splitlines()
    # 8 lines > 6: drop int(8 * 0.25) = 2 oldest, keep newest 6
    assert len(lines) == 6
    kept = [json.loads(l)["i"] for l in lines]
    assert kept == [2, 3, 4, 5, 6, 7]


def test_rotate_history_missing_file_noop(tmp_path):
    common._rotate_history(str(tmp_path / "nope.jsonl"))  # must not raise


def test_rotate_history_under_limit_unchanged(tmp_path):
    p = tmp_path / "h.jsonl"
    p.write_text('{"a": 1}\n{"a": 2}\n', encoding="utf-8")
    common._rotate_history(str(p))
    assert len(p.read_text(encoding="utf-8").splitlines()) == 2


# ---------------------------------------------------------------------------
# read_history
# ---------------------------------------------------------------------------

def test_read_history_missing_returns_empty(history_dir):
    assert common.read_history("absent") == []


def test_read_history_oldest_first(history_dir):
    common.append_history("vast", {"i": 1})
    common.append_history("vast", {"i": 2})
    common.append_history("vast", {"i": 3})
    assert [r["i"] for r in common.read_history("vast")] == [1, 2, 3]


def test_read_history_skips_blank_and_corrupt_lines(history_dir):
    (history_dir / "vast.jsonl").write_text(
        '{"i": 1}\n\nnot json\n{"i": 2}\n', encoding="utf-8")
    assert [r["i"] for r in common.read_history("vast")] == [1, 2]


def test_read_history_limit_last_n(history_dir):
    for i in range(5):
        common.append_history("vast", {"i": i})
    assert [r["i"] for r in common.read_history("vast", limit=2)] == [3, 4]


def test_read_history_limit_zero_returns_empty(history_dir):
    common.append_history("vast", {"i": 1})
    assert common.read_history("vast", limit=0) == []


# ---------------------------------------------------------------------------
# read_latest_json
# ---------------------------------------------------------------------------

def test_read_latest_json_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "DATA_LATEST", str(tmp_path))
    assert common.read_latest_json("composite") == {}


def test_read_latest_json_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "DATA_LATEST", str(tmp_path))
    common.atomic_write_json(common.latest_path("composite"), {"index": 42})
    assert common.read_latest_json("composite") == {"index": 42}


def test_read_latest_json_corrupt_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "DATA_LATEST", str(tmp_path))
    (tmp_path / "composite.json").write_text("{broken", encoding="utf-8")
    assert common.read_latest_json("composite") == {}
