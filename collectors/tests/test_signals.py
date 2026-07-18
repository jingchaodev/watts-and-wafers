from datetime import datetime, timedelta

import signals


def _dt(days_from_2026_01_01, hour=12):
    base = datetime(2026, 1, 1)
    d = base + timedelta(days=days_from_2026_01_01)
    return d.strftime("%Y-%m-%dT") + f"{hour:02d}:00:00Z"


def _vast_line(day, h100_sxm=None, h100_nvl=None, b200=None, hour=12):
    gpus = {}
    if h100_sxm is not None:
        gpus["H100 SXM"] = h100_sxm
    if h100_nvl is not None:
        gpus["H100 NVL"] = h100_nvl
    if b200 is not None:
        gpus["B200"] = b200
    return {"ts": _dt(day, hour), "gpus": gpus}


def _backfill_line(day, h100_sxm_price):
    return {
        "ts": _dt(day),
        "gpus": {"H100 SXM": {"offers": 1, "median_dph": h100_sxm_price}},
        "source": "github:example/tracker",
    }


def _hyperscaler_line(day, gpu, ondemand_gpu_hr, spot_vm_hr, gpus_per_vm=8):
    return {
        "ts": _dt(day),
        "azure": {
            "sku": {
                "gpu": gpu,
                "gpus_per_vm": gpus_per_vm,
                "ondemand_vm_hr": ondemand_gpu_hr * gpus_per_vm,
                "spot_vm_hr": spot_vm_hr,
                "ondemand_gpu_hr": ondemand_gpu_hr,
                "region": "eastus",
            }
        },
    }


def _neoclouds_line(day, h100=None, b200=None):
    providers = {}
    if h100 is not None or b200 is not None:
        providers["runpod"] = {}
        if h100 is not None:
            providers["runpod"]["H100"] = h100
        if b200 is not None:
            providers["runpod"]["B200"] = b200
    return {"ts": _dt(day), "providers": providers}


def _tokens_line(day, total_b_tokens):
    date_str = (datetime(2026, 1, 1) + timedelta(days=day)).strftime("%Y-%m-%d")
    return {"ts": _dt(day), "date": date_str, "total_b_tokens": total_b_tokens}


# ---------------------------------------------------------------------------
# h100_price: median-of-medians fold + splice + percentile
# ---------------------------------------------------------------------------

def test_h100_price_folds_sxm_and_nvl_via_median():
    line = _vast_line(0, h100_sxm={"offers": 10, "median_dph": 2.0}, h100_nvl={"offers": 5, "median_dph": 2.4})
    result = signals._h100_class_median_of_medians(line["gpus"])
    assert result == 2.2  # mean/median of exactly two values


def test_h100_price_missing_returns_none():
    assert signals._h100_class_median_of_medians({}) is None


def test_build_splice_uses_backfill_only_before_own_earliest_date():
    # backfill spans days 0-9, own data starts day 5
    backfill_hist = [_backfill_line(d, 1.5 + d * 0.01) for d in range(10)]
    vast_hist = [_vast_line(d, h100_sxm={"offers": 10, "median_dph": 2.0}) for d in range(5, 8)]

    daily_pairs, splice_active = signals.build_h100_price_splice(vast_hist, backfill_hist)

    assert splice_active is True
    dates = [d for d, _ in daily_pairs]
    # days 0-4 come from backfill (before day 5), days 5-7 from own data (own wins)
    assert dates[0] == "2026-01-01"
    own_dates = {d for d, v in daily_pairs if v == 2.0}
    assert "2026-01-06" in own_dates or "2026-01-08" in own_dates
    # own data overrides backfill on overlapping dates -- no overlap here since
    # backfill stops being used at day 5, but confirm no duplicate keys inflate the series
    assert len(dates) == len(set(dates))


def test_build_splice_no_backfill_used_once_own_covers_range():
    # own data starts BEFORE backfill's earliest date -> backfill entirely excluded
    backfill_hist = [_backfill_line(d, 1.5) for d in range(5, 10)]
    vast_hist = [_vast_line(d, h100_sxm={"offers": 10, "median_dph": 2.0}) for d in range(0, 12)]

    daily_pairs, splice_active = signals.build_h100_price_splice(vast_hist, backfill_hist)
    assert splice_active is False
    assert all(v == 2.0 for _, v in daily_pairs)


def test_compute_h100_price_percentile_mid_range():
    # 90 days of own data, flat at 2.0 except the latest which sits mid-pack
    vast_hist = []
    for d in range(90):
        price = 1.0 + (d % 10) * 0.1  # values cycle 1.0..1.9
        vast_hist.append(_vast_line(d, h100_sxm={"offers": 10, "median_dph": price}))
    result = signals.compute_h100_price(vast_hist, [])
    assert result["value"] is not None
    assert result["percentile"] is not None
    assert 0 <= result["percentile"] <= 100
    assert result["provenance"] is None  # no backfill needed/used
    assert len(result["spark"]) <= 30


def test_compute_h100_price_missing_data_returns_null_card():
    result = signals.compute_h100_price([], [])
    assert result["value"] is None
    assert result["key"] == "h100_price"
    assert "read" in result and result["read"]


def test_compute_h100_price_plausibility_guard_rejects_bad_price():
    # A price way outside validation.py's H100 band (0.5-16) must not be surfaced.
    vast_hist = [_vast_line(0, h100_sxm={"offers": 10, "median_dph": 999.0})]
    result = signals.compute_h100_price(vast_hist, [])
    assert result["value"] is None


# ---------------------------------------------------------------------------
# availability
# ---------------------------------------------------------------------------

def test_availability_short_history_uses_earliest_baseline_and_explains():
    vast_hist = [
        _vast_line(0, h100_sxm={"offers": 100, "median_dph": 2.0}),
        _vast_line(1, h100_sxm={"offers": 90, "median_dph": 2.0}),
        _vast_line(2, h100_sxm={"offers": 80, "median_dph": 2.0}),
    ]
    result = signals.compute_availability(vast_hist)
    assert result["percentile"] is None  # <14d of own history
    assert "history" in result["read"].lower() or "baseline" in result["read"].lower()
    assert result["value"] is not None  # still computes a delta vs earliest


def test_availability_percentile_null_before_14_days():
    vast_hist = [_vast_line(d, h100_sxm={"offers": 100 - d, "median_dph": 2.0}) for d in range(13)]
    result = signals.compute_availability(vast_hist)
    assert result["percentile"] is None


def test_availability_percentile_present_after_14_days():
    vast_hist = [_vast_line(d, h100_sxm={"offers": 100 - d, "median_dph": 2.0}) for d in range(20)]
    result = signals.compute_availability(vast_hist)
    assert result["percentile"] is not None


def test_availability_falling_offers_is_down_direction_and_hot_tone():
    vast_hist = [_vast_line(d, h100_sxm={"offers": 200 - d * 5, "median_dph": 2.0}) for d in range(20)]
    result = signals.compute_availability(vast_hist)
    assert result["direction"] == "down"
    assert result["tone"] == "hot"


def test_availability_rising_offers_is_up_direction_and_cold_tone():
    vast_hist = [_vast_line(d, h100_sxm={"offers": 50 + d * 5, "median_dph": 2.0}) for d in range(20)]
    result = signals.compute_availability(vast_hist)
    assert result["direction"] == "up"
    assert result["tone"] == "cold"


def test_availability_flat_within_deadband():
    vast_hist = [_vast_line(d, h100_sxm={"offers": 100, "median_dph": 2.0}) for d in range(20)]
    result = signals.compute_availability(vast_hist)
    assert result["direction"] == "flat"
    assert result["tone"] == "neutral"


def test_availability_missing_data_returns_null_card():
    result = signals.compute_availability([])
    assert result["value"] is None
    assert result["key"] == "availability"


# ---------------------------------------------------------------------------
# spot_discount
# ---------------------------------------------------------------------------

def test_spot_discount_computes_ratio():
    hist = [_hyperscaler_line(d, "H100", ondemand_gpu_hr=7.0, spot_vm_hr=8.0 * 8) for d in range(10)]
    # spot_vm_hr / gpus_per_vm = 8.0 spot_gpu_hr; ratio = 8.0/7.0
    result = signals.compute_spot_discount(hist)
    assert result["value"] is not None
    assert round(result["value"], 3) == round(8.0 / 7.0, 3)


def test_spot_discount_missing_spot_vm_hr_is_null_card():
    hist = [_hyperscaler_line(0, "H100", ondemand_gpu_hr=7.0, spot_vm_hr=None)]
    result = signals.compute_spot_discount(hist)
    assert result["value"] is None
    assert result["key"] == "spot_discount"


def test_spot_discount_no_h100_sku_is_null_card():
    hist = [_hyperscaler_line(0, "A100", ondemand_gpu_hr=4.0, spot_vm_hr=16.0)]
    result = signals.compute_spot_discount(hist)
    assert result["value"] is None


def test_spot_discount_thin_history_percentile_null():
    hist = [_hyperscaler_line(0, "H100", ondemand_gpu_hr=7.0, spot_vm_hr=8.0 * 8)]
    result = signals.compute_spot_discount(hist)
    assert result["percentile"] is None  # <5 points


# ---------------------------------------------------------------------------
# gen_ratio
# ---------------------------------------------------------------------------

def test_gen_ratio_computes_perf_adjusted_ratio():
    vast_hist = [_vast_line(0, h100_sxm={"offers": 10, "median_dph": 2.0}, b200={"offers": 5, "median_dph": 6.4})]
    result = signals.compute_gen_ratio(vast_hist, [])
    # (6.4 / 3.2) / 2.0 = 1.0
    assert result["value"] == 1.0


def test_gen_ratio_missing_b200_is_null_card():
    vast_hist = [_vast_line(0, h100_sxm={"offers": 10, "median_dph": 2.0})]
    result = signals.compute_gen_ratio(vast_hist, [])
    assert result["value"] is None
    assert result["key"] == "gen_ratio"


def test_gen_ratio_blends_vast_and_neoclouds_via_median():
    vast_hist = [_vast_line(0, h100_sxm={"offers": 10, "median_dph": 2.0}, b200={"offers": 5, "median_dph": 6.0})]
    neoclouds_hist = [_neoclouds_line(0, h100=2.2, b200=6.4)]
    result = signals.compute_gen_ratio(vast_hist, neoclouds_hist)
    assert result["value"] is not None


def test_gen_ratio_cold_tone_when_both_generations_fell_over_10pct_in_30d():
    vast_hist = []
    for d in range(31):
        if d == 0:
            h100, b200 = 4.0, 12.0
        else:
            h100, b200 = 2.0, 6.0  # -50% each, well past the 10% threshold
        vast_hist.append(_vast_line(d, h100_sxm={"offers": 10, "median_dph": h100}, b200={"offers": 5, "median_dph": b200}))
    result = signals.compute_gen_ratio(vast_hist, [])
    assert result["tone"] == "cold"


def test_gen_ratio_neutral_tone_when_prices_flat():
    vast_hist = [_vast_line(d, h100_sxm={"offers": 10, "median_dph": 2.0}, b200={"offers": 5, "median_dph": 6.4}) for d in range(31)]
    result = signals.compute_gen_ratio(vast_hist, [])
    assert result["tone"] == "neutral"


def test_gen_ratio_provenance_cites_coefficient():
    vast_hist = [_vast_line(0, h100_sxm={"offers": 10, "median_dph": 2.0}, b200={"offers": 5, "median_dph": 6.4})]
    result = signals.compute_gen_ratio(vast_hist, [])
    assert "3.2" in result["provenance"]


# ---------------------------------------------------------------------------
# token_growth
# ---------------------------------------------------------------------------

def test_token_growth_computes_30d_7dma_growth():
    # 60 days: first 30 flat at 100, next 30 flat at 150 (so 7dMA jumps ~50%)
    hist = []
    for d in range(60):
        val = 100.0 if d < 30 else 150.0
        hist.append(_tokens_line(d, val))
    result = signals.compute_token_growth(hist)
    assert result["value"] is not None
    assert result["value"] > 30  # meaningfully positive growth
    assert result["direction"] in ("up", "flat")


def test_token_growth_thin_history_is_null_card():
    hist = [_tokens_line(d, 100.0) for d in range(5)]
    result = signals.compute_token_growth(hist)
    assert result["value"] is None
    assert result["key"] == "token_growth"


def test_token_growth_flat_series_is_zero_growth():
    hist = [_tokens_line(d, 100.0) for d in range(60)]
    result = signals.compute_token_growth(hist)
    assert result["value"] == 0.0
    assert result["direction"] == "flat"
    assert result["tone"] == "neutral"


def test_token_growth_percentile_present_with_deep_history():
    hist = []
    for d in range(120):
        hist.append(_tokens_line(d, 100.0 + d))  # steadily growing
    result = signals.compute_token_growth(hist)
    assert result["percentile"] is not None


# ---------------------------------------------------------------------------
# shared: direction deadband + null-card shape
# ---------------------------------------------------------------------------

def test_direction_deadband_flat_within_2pct():
    assert signals._direction(1.9) == "flat"
    assert signals._direction(-1.9) == "flat"
    assert signals._direction(2.1) == "up"
    assert signals._direction(-2.1) == "down"
    assert signals._direction(None) == "flat"


def test_null_card_shape_matches_normal_card_keys():
    normal = signals.compute_gen_ratio(
        [_vast_line(0, h100_sxm={"offers": 10, "median_dph": 2.0}, b200={"offers": 5, "median_dph": 6.4})], []
    )
    null_card = signals.compute_gen_ratio([], [])
    assert set(normal.keys()) == set(null_card.keys())
    assert null_card["value"] is None
    assert null_card["read"]


# ---------------------------------------------------------------------------
# collect(): all 5 cards always present, never crashes on empty input
# ---------------------------------------------------------------------------

def test_collect_produces_all_five_cards_even_with_no_history(monkeypatch, tmp_path):
    monkeypatch.setattr(signals, "read_history", lambda name, limit=None: [])
    monkeypatch.setattr(signals, "_read_latest_json", lambda name: {})
    payload = signals.collect()
    keys = [c["key"] for c in payload["cards"]]
    assert keys == ["h100_price", "availability", "spot_discount", "gen_ratio", "token_growth"]
    for c in payload["cards"]:
        assert c["value"] is None
        assert c["read"]
    assert payload["composite"] == {"index": None, "label": None}
    assert payload["errors"] == []


def test_collect_card_computation_crash_yields_null_card_not_exception(monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError("boom")
    monkeypatch.setattr(signals, "compute_h100_price", _boom)
    monkeypatch.setattr(signals, "read_history", lambda name, limit=None: [])
    monkeypatch.setattr(signals, "_read_latest_json", lambda name: {})
    payload = signals.collect()
    h100_card = next(c for c in payload["cards"] if c["key"] == "h100_price")
    assert h100_card["value"] is None
    assert len(payload["errors"]) == 1
    assert payload["errors"][0]["card"] == "h100_price"
