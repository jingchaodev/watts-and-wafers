import composite


def _vast_hist(offers_series, dph_series):
    """Build synthetic vast.jsonl-shaped history: offers/median_dph on H100 SXM only."""
    out = []
    for offers, dph in zip(offers_series, dph_series):
        out.append({
            "ts": "2026-07-01T00:00:00Z",
            "gpus": {"H100 SXM": {"offers": offers, "median_dph": dph}},
        })
    return out


def _openrouter_hist(prices):
    return [{"ts": "2026-07-01T00:00:00Z", "frontier_median_completion_usd_per_m": p} for p in prices]


def _memory_hist(avgs):
    return [
        {"ts": "2026-07-01T00:00:00Z", "dram_spot": [{"item": "DDR5 16Gb (2Gx8) 4800/5600", "avg": a, "chg_pct": 0.0}]}
        for a in avgs
    ]


def test_compute_gpu_availability_short_history_is_flat():
    result = composite.compute_gpu_availability(_vast_hist([100, 100], [1.0, 1.0]))
    assert result["z"] == 0.0
    assert result["direction"] == "flat"


def test_compute_gpu_availability_falling_offers_is_positive_z():
    # offers steadily falling -> tightening -> positive z (negated raw z)
    series = [200, 190, 180, 170, 160, 150, 100]
    result = composite.compute_gpu_availability(_vast_hist(series, [1.0] * len(series)))
    assert result["z"] > 0
    assert result["direction"] == "up"


def test_compute_gpu_price_rising_price_is_positive_z():
    # 23 days flat at 1.0, then a 7d window that jumped to 3.0
    series = [1.0] * 23 + [3.0] * 7
    result = composite.compute_gpu_price(_vast_hist([100] * len(series), series))
    assert result["z"] > 0


def test_compute_token_economics_falling_price_is_positive_z():
    # frontier price falling -> demand tightening (per contract framing) -> positive z
    series = [20.0, 19.0, 18.0, 17.0, 16.0, 15.0, 5.0]
    result = composite.compute_token_economics(_openrouter_hist(series))
    assert result["z"] > 0


def test_compute_memory_flat_history_is_zero():
    result = composite.compute_memory(_memory_hist([50.0] * 10))
    assert result["z"] == 0.0
    assert result["direction"] == "flat"


def test_compute_memory_rising_avg_is_positive_z():
    # 23 days flat at 50.0, then a 7d window that jumped to 70.0
    series = [50.0] * 23 + [70.0] * 7
    result = composite.compute_memory(_memory_hist(series))
    assert result["z"] > 0


def test_compute_index_neutral_when_all_signals_flat():
    signal_map = {
        "gpu_availability": {"z": 0.0, "direction": "flat", "detail": "n/a"},
        "gpu_price": {"z": 0.0, "direction": "flat", "detail": "n/a"},
        "token_economics": {"z": 0.0, "direction": "flat", "detail": "n/a"},
        "memory": {"z": 0.0, "direction": "flat", "detail": "n/a"},
    }
    index, label, signals = composite.compute_index(signal_map)
    assert index == 50.0
    assert label == "NEUTRAL"
    assert len(signals) == 4
    for s in signals:
        assert set(s.keys()) == {"key", "weight", "z", "direction", "detail"}


def test_compute_index_surging_with_strong_positive_signals():
    signal_map = {
        "gpu_availability": {"z": 2.0, "direction": "up", "detail": "n/a"},
        "gpu_price": {"z": 2.0, "direction": "up", "detail": "n/a"},
        "token_economics": {"z": 2.0, "direction": "up", "detail": "n/a"},
        "memory": {"z": 2.0, "direction": "up", "detail": "n/a"},
    }
    index, label, signals = composite.compute_index(signal_map)
    # 50 + 12.5 * 2.0 * (0.35+0.15+0.25+0.25) = 50 + 12.5*2.0*1.0 = 75, clamped to 100 if higher
    assert index == 75.0
    assert label == "SURGING"


def test_compute_index_clamped_to_100():
    signal_map = {k: {"z": 10.0, "direction": "up", "detail": "n/a"} for k in composite.WEIGHTS}
    index, label, _ = composite.compute_index(signal_map)
    assert index == 100.0
    assert label == "SURGING"


def test_compute_index_clamped_to_0():
    signal_map = {k: {"z": -10.0, "direction": "down", "detail": "n/a"} for k in composite.WEIGHTS}
    index, label, _ = composite.compute_index(signal_map)
    assert index == 0.0
    assert label == "GLUT"


def test_compute_index_glut_softening_tightening_thresholds():
    # weights sum to 1.0, so index = 50 + 12.5*z_avg when all signals share z
    cases = [
        (-2.0, "GLUT"),       # 50 - 25 = 25
        (-0.9, "SOFTENING"),  # 50 - 11.25 = 38.75
        (0.0, "NEUTRAL"),     # 50
        (0.5, "TIGHTENING"),  # 50 + 6.25 = 56.25
        (1.5, "SURGING"),     # 50 + 18.75 = 68.75
    ]
    for z, expected_label in cases:
        signal_map = {k: {"z": z, "direction": "flat", "detail": "n/a"} for k in composite.WEIGHTS}
        index, label, _ = composite.compute_index(signal_map)
        assert label == expected_label, f"z={z} index={index} expected={expected_label} got={label}"
