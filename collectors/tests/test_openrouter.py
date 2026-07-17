import os

import openrouter

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


def test_parse_models_schema():
    raw = _load("openrouter_models.json")
    result = openrouter.parse_models(raw)

    assert set(result.keys()) == {"n_models", "models", "frontier_median_completion_usd_per_m"}
    assert result["n_models"] == 13  # fixture has 13 raw entries (before filtering)

    # openrouter/auto-beta has pricing "-1" (N/A sentinel) -> excluded
    ids = [m["id"] for m in result["models"]]
    assert "openrouter/auto-beta" not in ids

    # free models (price "0") ARE valid priced models (0.0 completion) -> included
    assert "cognitivecomputations/dolphin-mistral-24b-venice-edition:free" in ids

    # sorted descending by completion price
    prices = [m["completion_usd_per_m"] for m in result["models"]]
    assert prices == sorted(prices, reverse=True)

    for m in result["models"]:
        assert set(m.keys()) == {"id", "name", "prompt_usd_per_m", "completion_usd_per_m", "context"}

    # frontier_median computed from the most expensive models
    assert result["frontier_median_completion_usd_per_m"] is not None
    assert result["frontier_median_completion_usd_per_m"] > 0


def test_price_per_m_sentinel_and_missing():
    assert openrouter._price_per_m({"completion": "-1"}, "completion") is None
    assert openrouter._price_per_m({"completion": "0.000015"}, "completion") == 15.0
    assert openrouter._price_per_m({}, "completion") is None
    assert openrouter._price_per_m({"completion": "not-a-number"}, "completion") is None


def test_fetch_tokens_daily_is_documented_none():
    assert openrouter.fetch_tokens_daily() is None
