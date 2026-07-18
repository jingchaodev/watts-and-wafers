import crosscheck


# ---------------------------------------------------------------------------
# gather_prices
# ---------------------------------------------------------------------------

def test_gather_prices_combines_all_three_sources():
    vast_doc = {"gpus": {"H100 SXM": {"median_dph": 2.0}, "B200": {"median_dph": 4.0}}}
    neoclouds_doc = {"providers": {"runpod": {"H100": 2.1}, "datacrunch": {"H100": 2.3, "B200": 4.5}}}
    hyperscaler_doc = {"azure": {"ND96isr_H100_v5": {"gpu": "H100", "ondemand_gpu_hr": 6.98}}}

    by_gpu = crosscheck.gather_prices(vast_doc, neoclouds_doc, hyperscaler_doc)

    assert by_gpu["H100"] == {"vast": 2.0, "runpod": 2.1, "datacrunch": 2.3, "azure": 6.98}
    assert by_gpu["B200"] == {"vast": 4.0, "datacrunch": 4.5}


def test_gather_prices_azure_keeps_lowest_across_skus():
    hyperscaler_doc = {"azure": {
        "sku_a": {"gpu": "H100", "ondemand_gpu_hr": 8.0},
        "sku_b": {"gpu": "H100", "ondemand_gpu_hr": 6.5},
    }}
    by_gpu = crosscheck.gather_prices({}, {}, hyperscaler_doc)
    assert by_gpu["H100"]["azure"] == 6.5


def test_gather_prices_skips_none_and_unrecognized():
    vast_doc = {"gpus": {"H100 SXM": {"median_dph": None}, "UNKNOWN-CLASS": {"median_dph": 1.0}}}
    by_gpu = crosscheck.gather_prices(vast_doc, {}, {})
    assert by_gpu == {}


def test_gather_prices_empty_docs():
    assert crosscheck.gather_prices({}, {}, {}) == {}


# ---------------------------------------------------------------------------
# compute_flags
# ---------------------------------------------------------------------------

def test_compute_flags_no_deviation_no_flags():
    by_gpu = {"H100": {"vast": 2.0, "runpod": 2.1, "azure": 2.2}}
    assert crosscheck.compute_flags(by_gpu) == []


def test_compute_flags_single_provider_never_flagged():
    # 1 provider -> price == median always -> no-op regardless of value.
    by_gpu = {"H100": {"runpod": 999.0}}
    assert crosscheck.compute_flags(by_gpu) == []


def test_compute_flags_detects_low_outlier():
    # cohort median ~2.0, one provider at 0.2 -> ratio 0.1, way past 2.5x band.
    by_gpu = {"H100": {"vast": 2.0, "runpod": 2.1, "datacrunch": 0.2}}
    flags = crosscheck.compute_flags(by_gpu)
    assert len(flags) == 1
    assert flags[0]["gpu"] == "H100"
    assert flags[0]["provider"] == "datacrunch"
    assert flags[0]["price"] == 0.2
    assert flags[0]["ratio"] < 1


def test_compute_flags_detects_high_outlier():
    by_gpu = {"H100": {"vast": 2.0, "runpod": 2.1, "azure": 20.0}}
    flags = crosscheck.compute_flags(by_gpu)
    assert len(flags) == 1
    assert flags[0]["provider"] == "azure"
    assert flags[0]["ratio"] > 2.5


def test_compute_flags_just_under_threshold_not_flagged():
    # cohort median 2.0, provider price at exactly 2.49x (just under 2.5x) -> no flag.
    by_gpu = {"H100": {"vast": 2.0, "runpod": 2.0, "azure": 2.0 * 2.49}}
    flags = crosscheck.compute_flags(by_gpu)
    assert flags == []


def test_compute_flags_just_over_threshold_flagged():
    by_gpu = {"H100": {"vast": 2.0, "runpod": 2.0, "azure": 2.0 * 2.51}}
    flags = crosscheck.compute_flags(by_gpu)
    assert len(flags) == 1
    assert flags[0]["provider"] == "azure"


def test_compute_flags_multiple_gpu_classes_independent():
    by_gpu = {
        "H100": {"vast": 2.0, "runpod": 2.1},
        "B200": {"vast": 4.0, "runpod": 4.2, "azure": 40.0},
    }
    flags = crosscheck.compute_flags(by_gpu)
    assert len(flags) == 1
    assert flags[0]["gpu"] == "B200"
    assert flags[0]["provider"] == "azure"


def test_compute_flags_sorted_by_gpu_then_provider():
    by_gpu = {
        "H200": {"vast": 3.0, "runpod": 30.0, "datacrunch": 0.1},
        "H100": {"vast": 2.0, "runpod": 20.0},
    }
    flags = crosscheck.compute_flags(by_gpu)
    gpus = [f["gpu"] for f in flags]
    assert gpus == sorted(gpus)


# ---------------------------------------------------------------------------
# collect() integration (reads latest/*.json via _read_latest)
# ---------------------------------------------------------------------------

def test_collect_missing_files_records_errors_not_crash(tmp_path, monkeypatch):
    import common
    monkeypatch.setattr(common, "DATA_LATEST", str(tmp_path))
    monkeypatch.setattr(crosscheck, "latest_path", lambda name: str(tmp_path / f"{name}.json"))

    payload = crosscheck.collect()

    assert payload["flags"] == []
    assert len(payload["errors"]) == 3
    assert "asof" in payload


def test_collect_with_real_files(tmp_path, monkeypatch):
    import json
    (tmp_path / "vast.json").write_text(json.dumps({"gpus": {"H100 SXM": {"median_dph": 2.0}}}))
    (tmp_path / "neoclouds.json").write_text(json.dumps(
        {"providers": {"runpod": {"H100": 2.1}, "datacrunch": {"H100": 20.0}}}
    ))
    (tmp_path / "hyperscaler.json").write_text(json.dumps({"azure": {}}))

    monkeypatch.setattr(crosscheck, "latest_path", lambda name: str(tmp_path / f"{name}.json"))

    payload = crosscheck.collect()

    assert payload["errors"] == []
    assert len(payload["flags"]) == 1
    assert payload["flags"][0]["provider"] == "datacrunch"
