import signal_events


def _card(key, percentile, delta_7d_pct=0.0, title=None):
    return {
        "key": key,
        "title": title or key,
        "percentile": percentile,
        "delta_7d_pct": delta_7d_pct,
        "window_days": 90,
    }


def _signals_payload(cards, label="NEUTRAL", asof="2026-07-18T00:00:00Z"):
    return {"asof": asof, "cards": cards, "composite": {"index": 50.0, "label": label}, "errors": []}


# ---------------------------------------------------------------------------
# percentile_cross
# ---------------------------------------------------------------------------

def test_percentile_cross_fires_on_entering_low_band():
    cur = _signals_payload([_card("availability", percentile=8)])
    prev = _signals_payload([_card("availability", percentile=40)])
    events = signal_events.detect_percentile_cross_events(cur, {c["key"]: c for c in prev["cards"]}, "2026-07-18")
    assert len(events) == 1
    assert events[0]["signal"] == "availability"
    assert events[0]["kind"] == "percentile_cross"
    assert events[0]["direction"] == "down"


def test_percentile_cross_fires_on_entering_high_band():
    cur = _signals_payload([_card("token_growth", percentile=93)])
    prev_cards = {"token_growth": _card("token_growth", percentile=60)}
    events = signal_events.detect_percentile_cross_events(cur, prev_cards, "2026-07-18")
    assert len(events) == 1
    assert events[0]["direction"] == "up"


def test_percentile_cross_does_not_refire_while_still_in_same_band():
    cur = _signals_payload([_card("availability", percentile=5)])
    prev_cards = {"availability": _card("availability", percentile=8)}  # already "low" last run
    events = signal_events.detect_percentile_cross_events(cur, prev_cards, "2026-07-18")
    assert events == []


def test_percentile_cross_no_event_when_percentile_none():
    cur = _signals_payload([_card("spot_discount", percentile=None)])
    events = signal_events.detect_percentile_cross_events(cur, {}, "2026-07-18")
    assert events == []


def test_percentile_cross_mid_range_no_event():
    cur = _signals_payload([_card("h100_price", percentile=50)])
    prev_cards = {"h100_price": _card("h100_price", percentile=8)}
    events = signal_events.detect_percentile_cross_events(cur, prev_cards, "2026-07-18")
    assert events == []


# ---------------------------------------------------------------------------
# label_flip
# ---------------------------------------------------------------------------

def test_label_flip_fires_on_change():
    cur = _signals_payload([], label="TIGHTENING")
    prev = {"label": "NEUTRAL"}
    events = signal_events.detect_label_flip_event(cur, prev, "2026-07-18")
    assert len(events) == 1
    assert events[0]["kind"] == "label_flip"
    assert events[0]["direction"] == "up"
    assert "NEUTRAL" in events[0]["detail"] and "TIGHTENING" in events[0]["detail"]


def test_label_flip_no_event_when_unchanged():
    cur = _signals_payload([], label="NEUTRAL")
    prev = {"label": "NEUTRAL"}
    events = signal_events.detect_label_flip_event(cur, prev, "2026-07-18")
    assert events == []


def test_label_flip_downgrade_direction():
    cur = _signals_payload([], label="SOFTENING")
    prev = {"label": "TIGHTENING"}
    events = signal_events.detect_label_flip_event(cur, prev, "2026-07-18")
    assert events[0]["direction"] == "down"


def test_label_flip_no_prior_state_no_event():
    cur = _signals_payload([], label="NEUTRAL")
    events = signal_events.detect_label_flip_event(cur, None, "2026-07-18")
    assert events == []


# ---------------------------------------------------------------------------
# shock
# ---------------------------------------------------------------------------

def test_shock_fires_when_availability_delta_exceeds_30pct():
    cur = _signals_payload([_card("availability", percentile=50, delta_7d_pct=-32.0)])
    events = signal_events.detect_shock_events(cur, "2026-07-18")
    assert len(events) == 1
    assert events[0]["kind"] == "shock"
    assert events[0]["direction"] == "down"


def test_shock_does_not_fire_under_threshold():
    cur = _signals_payload([_card("availability", percentile=50, delta_7d_pct=-10.0)])
    events = signal_events.detect_shock_events(cur, "2026-07-18")
    assert events == []


def test_shock_fires_upward_too():
    cur = _signals_payload([_card("availability", percentile=50, delta_7d_pct=45.0)])
    events = signal_events.detect_shock_events(cur, "2026-07-18")
    assert events[0]["direction"] == "up"


def test_shock_ignores_other_signals():
    cur = _signals_payload([_card("h100_price", percentile=50, delta_7d_pct=-90.0)])
    events = signal_events.detect_shock_events(cur, "2026-07-18")
    assert events == []


# ---------------------------------------------------------------------------
# cooldown dedup
# ---------------------------------------------------------------------------

def test_cooldown_suppresses_repeat_within_7_days():
    candidates = [{"date": "2026-07-18", "signal": "availability", "kind": "shock", "direction": "down", "detail": "x"}]
    history = [{"date": "2026-07-15", "signal": "availability", "kind": "shock", "direction": "down", "detail": "y"}]
    kept = signal_events.apply_cooldown(candidates, history, "2026-07-18")
    assert kept == []


def test_cooldown_allows_after_7_days():
    candidates = [{"date": "2026-07-18", "signal": "availability", "kind": "shock", "direction": "down", "detail": "x"}]
    history = [{"date": "2026-07-10", "signal": "availability", "kind": "shock", "direction": "down", "detail": "y"}]
    kept = signal_events.apply_cooldown(candidates, history, "2026-07-18")
    assert len(kept) == 1


def test_cooldown_different_direction_not_suppressed():
    candidates = [{"date": "2026-07-18", "signal": "availability", "kind": "shock", "direction": "up", "detail": "x"}]
    history = [{"date": "2026-07-17", "signal": "availability", "kind": "shock", "direction": "down", "detail": "y"}]
    kept = signal_events.apply_cooldown(candidates, history, "2026-07-18")
    assert len(kept) == 1


def test_cooldown_different_signal_not_suppressed():
    candidates = [{"date": "2026-07-18", "signal": "h100_price", "kind": "percentile_cross", "direction": "down", "detail": "x"}]
    history = [{"date": "2026-07-17", "signal": "availability", "kind": "percentile_cross", "direction": "down", "detail": "y"}]
    kept = signal_events.apply_cooldown(candidates, history, "2026-07-18")
    assert len(kept) == 1


def test_cooldown_no_prior_history_never_suppresses():
    candidates = [{"date": "2026-07-18", "signal": "availability", "kind": "shock", "direction": "down", "detail": "x"}]
    kept = signal_events.apply_cooldown(candidates, [], "2026-07-18")
    assert len(kept) == 1


# ---------------------------------------------------------------------------
# compute_events: end-to-end pure composition
# ---------------------------------------------------------------------------

def test_compute_events_combines_all_kinds():
    cur = _signals_payload(
        [
            _card("availability", percentile=5, delta_7d_pct=-35.0),
            _card("h100_price", percentile=50, delta_7d_pct=0.0),
        ],
        label="SURGING",
    )
    prev_state = {
        "cards": [{"key": "availability", "percentile": 50}, {"key": "h100_price", "percentile": 50}],
        "composite": {"label": "NEUTRAL"},
    }
    events = signal_events.compute_events(cur, prev_state, [])
    kinds = {e["kind"] for e in events}
    assert kinds == {"percentile_cross", "label_flip", "shock"}


def test_compute_events_empty_when_nothing_notable():
    cur = _signals_payload([_card("availability", percentile=50, delta_7d_pct=1.0)], label="NEUTRAL")
    prev_state = {
        "cards": [{"key": "availability", "percentile": 50}],
        "composite": {"label": "NEUTRAL"},
    }
    events = signal_events.compute_events(cur, prev_state, [])
    assert events == []


def test_compute_events_no_prev_state_still_works():
    cur = _signals_payload([_card("availability", percentile=50, delta_7d_pct=1.0)], label="NEUTRAL")
    events = signal_events.compute_events(cur, None, [])
    assert events == []
