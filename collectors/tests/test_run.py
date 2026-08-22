"""Tests for run.py — the CLI entry point the VPS cron invokes.

Covers group/only dispatch, per-collector exception isolation, exit-code
semantics, and the --json summary output. Real collectors are never invoked;
COLLECTORS/GROUPS are swapped for fakes via monkeypatch.
"""
import json

import pytest

import run


class FakeCollector:
    def __init__(self, rc=0, exc=None):
        self.rc = rc
        self.exc = exc
        self.calls = 0

    def main(self):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.rc


@pytest.fixture
def fakes(monkeypatch):
    """Replace COLLECTORS with two fakes and GROUPS with a two-entry group."""
    a = FakeCollector(rc=0)
    b = FakeCollector(rc=0)
    monkeypatch.setitem(run.COLLECTORS, "alpha", a)
    monkeypatch.setitem(run.COLLECTORS, "beta", b)
    monkeypatch.setattr(run, "GROUPS", {"hourly": ["alpha", "beta"]})
    return a, b


# ---------------------------------------------------------------------------
# Static shape
# ---------------------------------------------------------------------------

def test_group_definitions_cover_all_collectors():
    declared = set(run.GROUPS["hourly"]) | set(run.GROUPS["daily"])
    assert declared == set(run.COLLECTORS.keys())


# ---------------------------------------------------------------------------
# run_one isolation
# ---------------------------------------------------------------------------

def test_run_one_success(monkeypatch):
    fake = FakeCollector(rc=0)
    monkeypatch.setitem(run.COLLECTORS, "alpha", fake)
    assert run.run_one("alpha") is True
    assert fake.calls == 1


def test_run_one_nonzero_rc(monkeypatch, capsys):
    fake = FakeCollector(rc=3)
    monkeypatch.setitem(run.COLLECTORS, "alpha", fake)
    assert run.run_one("alpha") is False
    assert "exited nonzero (3)" in capsys.readouterr().err


def test_run_one_crash_is_isolated(monkeypatch, capsys):
    fake = FakeCollector(exc=RuntimeError("boom"))
    monkeypatch.setitem(run.COLLECTORS, "alpha", fake)
    assert run.run_one("alpha") is False
    assert "CRASHED" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main() dispatch + exit codes
# ---------------------------------------------------------------------------

def test_main_only_runs_single_collector(fakes, capsys):
    a, b = fakes
    assert run.main(["--only", "alpha"]) == 0
    assert a.calls == 1
    assert b.calls == 0


def test_main_group_runs_in_order(fakes, capsys):
    a, b = fakes
    assert run.main(["--group", "hourly"]) == 0
    assert (a.calls, b.calls) == (1, 1)


def test_main_all_fail_exits_1(monkeypatch, capsys):
    monkeypatch.setitem(run.COLLECTORS, "alpha", FakeCollector(exc=ValueError("x")))
    monkeypatch.setitem(run.COLLECTORS, "beta", FakeCollector(rc=2))
    monkeypatch.setattr(run, "GROUPS", {"hourly": ["alpha", "beta"]})
    assert run.main(["--group", "hourly"]) == 1


def test_main_partial_success_exits_0(fakes, monkeypatch, capsys):
    a, b = fakes
    # make beta fail: swap in a failing fake
    monkeypatch.setitem(run.COLLECTORS, "beta", FakeCollector(exc=RuntimeError("x")))
    assert run.main(["--group", "hourly"]) == 0  # alpha ok -> overall 0


def test_main_requires_group_or_only(capsys):
    with pytest.raises(SystemExit):
        run.main([])


def test_main_rejects_unknown_choice(capsys):
    with pytest.raises(SystemExit):
        run.main(["--only", "nope"])


# ---------------------------------------------------------------------------
# --json summary
# ---------------------------------------------------------------------------

def test_main_json_summary_success(fakes, capsys):
    a, b = fakes
    assert run.main(["--group", "hourly", "--json"]) == 0
    out, err = capsys.readouterr()
    summary = json.loads(out)
    assert summary == {"group": "hourly", "ok": 2, "total": 2, "failed": [], "exit": 0}
    # human progress lines must NOT pollute stdout in --json mode
    assert "[run]" not in out
    assert "[run] --- alpha ---" in err


def test_main_json_summary_failures(monkeypatch, capsys):
    monkeypatch.setitem(run.COLLECTORS, "alpha", FakeCollector(rc=0))
    monkeypatch.setitem(run.COLLECTORS, "beta", FakeCollector(exc=RuntimeError("x")))
    monkeypatch.setattr(run, "GROUPS", {"hourly": ["alpha", "beta"]})
    assert run.main(["--group", "hourly", "--json"]) == 0
    out, _ = capsys.readouterr()
    summary = json.loads(out)
    assert summary["ok"] == 1
    assert summary["total"] == 2
    assert summary["failed"] == ["beta"]
    assert summary["exit"] == 0


def test_main_json_single_only(fakes, capsys):
    a, b = fakes
    assert run.main(["--only", "alpha", "--json"]) == 0
    out, _ = capsys.readouterr()
    assert json.loads(out)["group"] == "alpha"
    assert a.calls == 1 and b.calls == 0
