import json
import os

import validation


# ---------------------------------------------------------------------------
# check_price
# ---------------------------------------------------------------------------

def test_check_price_ok_within_band():
    assert validation.check_price("H100", 2.5) == "ok"
    assert validation.check_price("H200", 5.0) == "ok"
    assert validation.check_price("B200", 4.0) == "ok"
    assert validation.check_price("GB200", 10.0) == "ok"
    assert validation.check_price("A100", 1.5) == "ok"
    assert validation.check_price("L40S", 1.0) == "ok"
    assert validation.check_price("RTX 4090", 0.35) == "ok"
    assert validation.check_price("MI300X", 2.0) == "ok"


def test_check_price_band_boundaries_inclusive():
    lo, hi = validation.PRICE_BANDS_USD_PER_GPU_HR["H100"]
    assert validation.check_price("H100", lo) == "ok"
    assert validation.check_price("H100", hi) == "ok"


def test_check_price_below_floor_is_violation():
    result = validation.check_price("H100", 0.04)
    assert result != "ok"
    assert "below plausibility floor" in result


def test_check_price_above_ceiling_is_violation():
    result = validation.check_price("H100", 45.0)
    assert result != "ok"
    assert "above plausibility ceiling" in result


def test_check_price_catches_per_node_vs_per_gpu_unit_error():
    # An H100 8-GPU node's total dph (e.g. $28/hr for the whole node)
    # mistakenly reported as a per-GPU price should be flagged.
    result = validation.check_price("H100 SXM", 28.0)
    assert result != "ok"


def test_check_price_catches_cents_vs_dollars_unit_error():
    # $0.019/hr is what you'd get if a real ~$1.90/hr price were divided by
    # 100 (cents mistaken for dollars).
    result = validation.check_price("A100", 0.019)
    assert result != "ok"


def test_check_price_none_price_is_ok():
    assert validation.check_price("H100", None) == "ok"


def test_check_price_non_numeric_is_violation():
    result = validation.check_price("H100", "not-a-number")
    assert result != "ok"
    assert "non-numeric" in result


def test_check_price_unknown_gpu_class_is_ok():
    # No band defined -> nothing to enforce, not a violation.
    assert validation.check_price("EXOTIC-GPU-9000", 999.0) == "ok"


def test_canonical_gpu_class_aliases():
    assert validation.canonical_gpu_class("H100 SXM") == "H100"
    assert validation.canonical_gpu_class("H100 NVL") == "H100"
    assert validation.canonical_gpu_class("A100 SXM4") == "A100"
    assert validation.canonical_gpu_class("RTX 4090") == "RTX 4090"
    assert validation.canonical_gpu_class("GB200") == "GB200"
    assert validation.canonical_gpu_class(None) is None
    assert validation.canonical_gpu_class("") is None


# ---------------------------------------------------------------------------
# check_relations
# ---------------------------------------------------------------------------

def test_check_relations_spot_exceeds_ondemand_is_violation():
    record = {"spot_dph": 10.0, "ondemand_dph": 5.0}
    violations = validation.check_relations(record)
    assert len(violations) == 1
    assert "spot" in violations[0]


def test_check_relations_spot_within_1_05x_tolerance_is_ok():
    record = {"spot_dph": 5.2, "ondemand_dph": 5.0}  # 1.04x, within tolerance
    assert validation.check_relations(record) == []


def test_check_relations_spot_just_over_1_05x_is_violation():
    record = {"spot_dph": 5.3, "ondemand_dph": 5.0}  # 1.06x
    violations = validation.check_relations(record)
    assert len(violations) == 1


def test_check_relations_p25_exceeds_median_is_violation():
    record = {"p25_dph": 3.0, "median_dph": 2.0}
    violations = validation.check_relations(record)
    assert any("p25" in v for v in violations)


def test_check_relations_p25_le_median_is_ok():
    record = {"p25_dph": 1.5, "median_dph": 2.0}
    assert validation.check_relations(record) == []


def test_check_relations_implausible_spread_is_violation():
    record = {"p25_dph": 0.1, "median_dph": 5.0}  # 50x spread
    violations = validation.check_relations(record)
    assert any("10x" in v for v in violations)


def test_check_relations_negative_offers_is_violation():
    record = {"offers": -5}
    violations = validation.check_relations(record)
    assert any("offers" in v for v in violations)


def test_check_relations_negative_total_gpus_is_violation():
    record = {"total_gpus": -1}
    violations = validation.check_relations(record)
    assert any("total_gpus" in v for v in violations)


def test_check_relations_zero_offers_is_ok():
    record = {"offers": 0, "total_gpus": 0}
    assert validation.check_relations(record) == []


def test_check_relations_missing_fields_skipped_not_flagged():
    assert validation.check_relations({}) == []
    assert validation.check_relations({"median_dph": 2.0}) == []


def test_check_relations_multiple_violations_all_reported():
    record = {"spot_dph": 10.0, "ondemand_dph": 5.0, "p25_dph": 3.0, "median_dph": 2.0, "offers": -1}
    violations = validation.check_relations(record)
    assert len(violations) == 3


# ---------------------------------------------------------------------------
# quarantine
# ---------------------------------------------------------------------------

def test_quarantine_appends_json_line(tmp_path, monkeypatch):
    qpath = str(tmp_path / "quarantine.jsonl")
    monkeypatch.setattr(validation, "QUARANTINE_PATH", qpath)

    validation.quarantine("vast", {"gpu_name": "H100 SXM", "median_dph": 45.0}, "too high")

    assert os.path.exists(qpath)
    with open(qpath) as f:
        lines = f.read().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["source"] == "vast"
    assert rec["item"] == {"gpu_name": "H100 SXM", "median_dph": 45.0}
    assert rec["reason"] == "too high"
    assert "ts" in rec


def test_quarantine_multiple_appends_multiple_lines(tmp_path, monkeypatch):
    qpath = str(tmp_path / "quarantine.jsonl")
    monkeypatch.setattr(validation, "QUARANTINE_PATH", qpath)

    validation.quarantine("vast", {"a": 1}, "reason1")
    validation.quarantine("hyperscaler", {"b": 2}, "reason2")

    with open(qpath) as f:
        lines = f.read().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["source"] == "vast"
    assert json.loads(lines[1])["source"] == "hyperscaler"


def test_quarantine_creates_parent_dir(tmp_path, monkeypatch):
    qpath = str(tmp_path / "nested" / "dir" / "quarantine.jsonl")
    monkeypatch.setattr(validation, "QUARANTINE_PATH", qpath)

    validation.quarantine("vast", {"a": 1}, "reason")

    assert os.path.exists(qpath)


# ---------------------------------------------------------------------------
# filter_prices
# ---------------------------------------------------------------------------

def test_filter_prices_drops_and_quarantines_bad_entries(tmp_path, monkeypatch):
    qpath = str(tmp_path / "quarantine.jsonl")
    monkeypatch.setattr(validation, "QUARANTINE_PATH", qpath)

    raw = {"H100": 2.5, "H200": 999.0, "RTX 4090": 0.35}
    clean = validation.filter_prices("neoclouds", raw, quarantine_source="runpod")

    assert clean == {"H100": 2.5, "RTX 4090": 0.35}
    with open(qpath) as f:
        lines = [json.loads(line) for line in f.read().splitlines()]
    assert len(lines) == 1
    assert lines[0]["source"] == "runpod"
    assert lines[0]["item"]["gpu"] == "H200"


def test_filter_prices_all_ok_returns_unchanged(tmp_path, monkeypatch):
    qpath = str(tmp_path / "quarantine.jsonl")
    monkeypatch.setattr(validation, "QUARANTINE_PATH", qpath)

    raw = {"H100": 2.5, "L40S": 1.0}
    clean = validation.filter_prices("neoclouds", raw)

    assert clean == raw
    assert not os.path.exists(qpath)


def test_filter_prices_empty_input():
    assert validation.filter_prices("neoclouds", {}) == {}
    assert validation.filter_prices("neoclouds", None) == {}
