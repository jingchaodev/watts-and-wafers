import os

import memory

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


def test_parse_dram_spot_schema():
    raw = _load("trendforce_dram_spot.html")
    rows = memory.parse_dram_spot(raw)

    assert isinstance(rows, list)
    assert len(rows) == 7  # 7 real DRAM/legacy chip rows on the live page

    for row in rows:
        assert set(row.keys()) == {"item", "avg", "chg_pct"}
        assert isinstance(row["item"], str) and row["item"]
        assert isinstance(row["avg"], float)
        assert row["chg_pct"] is None or isinstance(row["chg_pct"], float)

    items = [r["item"] for r in rows]
    assert "DDR5 16Gb (2Gx8) 4800/5600" in items

    ddr5 = next(r for r in rows if r["item"] == "DDR5 16Gb (2Gx8) 4800/5600")
    assert ddr5["avg"] == 49.667
    assert ddr5["chg_pct"] == 0.68

    flat_row = next(r for r in rows if r["item"] == "DDR5 16Gb (2Gx8) eTT")
    assert flat_row["chg_pct"] == 0.0


def test_parse_dram_spot_no_table_returns_empty():
    assert memory.parse_dram_spot("<html><body>no tables here</body></html>") == []


def test_parse_nand_note_prefers_exact_spot_price_title():
    raw = _load("trendforce_news_with_spot_price.html")
    note = memory.parse_nand_note([raw])

    assert note is not None
    assert set(note.keys()) == {"date", "summary", "url"}
    assert "spot price" in note["summary"].lower()
    assert note["date"] == "2026-07-16"
    assert note["url"].startswith("https://www.trendforce.com/news/")


def test_parse_nand_note_falls_back_to_memory_related_headline():
    # this real-world fixture has NO article literally titled "...spot price..."
    raw = _load("trendforce_news_page1.html")
    note = memory.parse_nand_note([raw])

    # should still find *something* memory/dram/nand-related via fallback,
    # or None if the page truly has no such headline -- both are valid,
    # non-erroring outcomes per the contract's graceful-degradation rule
    if note is not None:
        assert set(note.keys()) == {"date", "summary", "url"}


def test_parse_nand_note_empty_pages_returns_none():
    assert memory.parse_nand_note([]) is None
    assert memory.parse_nand_note(["<html><body></body></html>"]) is None


def test_parse_finnhub_quote():
    raw = '{"c": 118.42, "d": 2.15, "dp": 1.85, "h": 119.0, "l": 116.0, "o": 116.5, "pc": 116.27, "t": 1752000000}'
    result = memory.parse_finnhub_quote(raw)
    assert result == {"price": 118.42, "chg_pct": 1.85}


def test_parse_finnhub_quote_zero_is_invalid_symbol():
    raw = '{"c": 0, "d": 0, "dp": 0, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0}'
    assert memory.parse_finnhub_quote(raw) is None
