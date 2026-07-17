#!/usr/bin/env python3
"""Memory (DRAM/NAND) collector — spot prices + news + equity proxies (daily).

Sources:
  1. TrendForce DRAM spot price table (static HTML, no auth):
     https://www.trendforce.com/price/dram/dram_spot
     Scraped via regex against the first `<table class="price-table">` block.
     Columns (left to right): item name, Daily High, Daily Low, Session High,
     Session Low, Session Average ("avg"), Session Change % ("chg_pct").
  2. TrendForce news listing, to find the latest "Memory Spot Price" digest
     article for nand_note.summary (title+date+url only; body not parsed).
     Investigated live: the general news feed
     (https://www.trendforce.com/news/, /news/page/2/, ...) does not always
     carry an article literally titled "Memory Spot Price" on its first
     couple of pages (that recurring digest title publishes on its own
     cadence). Per the graceful-degradation philosophy, we search a small,
     capped number of listing pages for a title matching
     /memory.*spot.*price|dram.*spot.*price/i, and if none is found we fall
     back to the single most recent memory/DRAM-related headline instead of
     erroring. This fallback is explicit and documented, not silent.
  3. Equity proxies (MU, 000660.KS) via Finnhub REST, ONLY if FINNHUB_KEY is
     set in the environment; otherwise proxies = {} with no error (per spec
     — this collector never reads /root/.skill-secrets.env, env only).

Writes data/latest/memory.json per docs/DATA_CONTRACT.md.
"""
import html
import json
import os
import re
import sys
from urllib.parse import quote

from common import atomic_write_json, append_history, fetch_url, iso_utc_now, latest_path

DRAM_SPOT_URL = "https://www.trendforce.com/price/dram/dram_spot"
NEWS_LIST_URL = "https://www.trendforce.com/news/"
NEWS_PAGE_URL = "https://www.trendforce.com/news/page/{n}/"
NEWS_MAX_PAGES = 2  # small, capped — this is a "nice to have" note field

MEMORY_TITLE_RE = re.compile(r"(memory.*spot.*price|dram.*spot.*price)", re.I)
MEMORY_FALLBACK_RE = re.compile(r"(memory|dram|nand)", re.I)

FINNHUB_QUOTE_URL = "https://finnhub.io/api/v1/quote"
PROXY_SYMBOLS = ("MU", "000660.KS")


# ---------------------------------------------------------------------------
# DRAM spot table
# ---------------------------------------------------------------------------

_TABLE_RE = re.compile(
    r'<table[^>]*class="[^"]*price-table[^"]*"[^>]*>(.*?)</table>', re.S
)
_ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
_ITEM_RE = re.compile(
    r'<span[^>]*data-toggle="tooltip"[^>]*>\s*([^<]+?)\s*</span>', re.S
)
_NUM_CELL_RE = re.compile(
    r'<td[^>]*class="[^"]*lcd-num-l[^"]*"[^>]*>\s*([^<]*?)\s*</td>', re.S
)
_TREND_RE = re.compile(
    r'<span class="(rise-trend|fall-trend|flat-trend)">.*?([\d.]+)\s*%',
    re.S,
)


def _parse_trend(cell_html):
    """Return signed chg_pct float from a `.percent-cell` block, or None."""
    m = _TREND_RE.search(cell_html)
    if not m:
        return None
    cls, num = m.group(1), m.group(2)
    try:
        v = float(num)
    except ValueError:
        return None
    if cls == "fall-trend":
        v = -abs(v)
    elif cls == "rise-trend":
        v = abs(v)
    else:  # flat-trend
        v = 0.0
    return v


def fetch_dram_spot(timeout=25, retries=2):
    return fetch_url(DRAM_SPOT_URL, timeout=timeout, retries=retries)


def parse_dram_spot(raw_html_text):
    """Pure parse: DRAM spot page HTML -> list of {"item","avg","chg_pct"}.

    Robust to item-name changes (no hardcoded item list) — walks every <tr>
    in the first price-table block and extracts whatever name/numbers it
    finds. Rows missing an item name, an average column, or a trend cell are
    skipped rather than raising.
    """
    tables = _TABLE_RE.findall(raw_html_text)
    if not tables:
        return []

    rows = _ROW_RE.findall(tables[0])
    out = []
    for row in rows:
        item_m = _ITEM_RE.search(row)
        if not item_m:
            continue  # header row or malformed row
        item = html.unescape(item_m.group(1)).strip()

        nums = _NUM_CELL_RE.findall(row)
        if len(nums) < 5:
            continue
        try:
            avg = float(nums[4])  # Session Average is the 5th lcd-num-l cell
        except ValueError:
            continue

        chg_pct = _parse_trend(row)

        out.append({"item": item, "avg": round(avg, 4), "chg_pct": chg_pct})
    return out


# ---------------------------------------------------------------------------
# News listing -> nand_note
# ---------------------------------------------------------------------------

_ARTICLE_RE = re.compile(
    r'<a[^>]+href="(https://www\.trendforce\.com/news/(\d{4})/(\d{2})/(\d{2})/[^"]+)"[^>]*>(.*?)</a>',
    re.S,
)


def fetch_news_page(n, timeout=25, retries=2):
    url = NEWS_LIST_URL if n == 1 else NEWS_PAGE_URL.format(n=n)
    return fetch_url(url, timeout=timeout, retries=retries)


def _extract_articles(raw_html_text):
    """Pure parse: one news listing page -> list of {"title","date","url"}."""
    out = []
    for href, y, m, d, inner in _ARTICLE_RE.findall(raw_html_text):
        text = re.sub(r"<[^>]+>", " ", inner)
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        out.append({"title": text, "date": f"{y}-{m}-{d}", "url": href})
    return out


def parse_nand_note(pages_html):
    """Pure parse: list of raw news-listing page HTML -> nand_note dict or None.

    Prefers a title matching /memory.*spot.*price|dram.*spot.*price/i; falls
    back to the most recent memory/DRAM/NAND-related headline if no exact
    "spot price" digest title is found within the fetched pages.
    """
    seen_urls = set()
    all_articles = []
    for raw in pages_html:
        for art in _extract_articles(raw):
            if art["url"] in seen_urls:
                continue
            seen_urls.add(art["url"])
            all_articles.append(art)

    for art in all_articles:
        if MEMORY_TITLE_RE.search(art["title"]):
            return {
                "date": art["date"],
                "summary": art["title"],
                "url": art["url"],
            }

    for art in all_articles:
        if MEMORY_FALLBACK_RE.search(art["title"]):
            return {
                "date": art["date"],
                "summary": art["title"],
                "url": art["url"],
            }

    return None


# ---------------------------------------------------------------------------
# Equity proxies (Finnhub, optional)
# ---------------------------------------------------------------------------

def fetch_finnhub_quote(symbol, api_key, timeout=25, retries=2):
    url = f"{FINNHUB_QUOTE_URL}?symbol={quote(symbol)}&token={quote(api_key)}"
    return fetch_url(url, timeout=timeout, retries=retries)


def parse_finnhub_quote(raw_json_text):
    """Pure parse: Finnhub /quote response -> {"price","chg_pct"} or None."""
    doc = json.loads(raw_json_text)
    price = doc.get("c")
    chg_pct = doc.get("dp")
    if price in (None, 0):
        return None
    return {
        "price": round(float(price), 4),
        "chg_pct": round(float(chg_pct), 4) if chg_pct is not None else None,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def collect():
    errors = []

    dram_spot = []
    try:
        raw = fetch_dram_spot()
        dram_spot = parse_dram_spot(raw)
    except Exception as e:  # noqa: BLE001
        errors.append({"source": "dram_spot", "error": repr(e)})
        print(f"[memory] dram_spot ERROR: {e}", file=sys.stderr)

    nand_note = None
    try:
        pages = [fetch_news_page(n) for n in range(1, NEWS_MAX_PAGES + 1)]
        nand_note = parse_nand_note(pages)
    except Exception as e:  # noqa: BLE001
        errors.append({"source": "nand_note", "error": repr(e)})
        print(f"[memory] nand_note ERROR: {e}", file=sys.stderr)

    proxies = {}
    api_key = os.environ.get("FINNHUB_KEY")
    if api_key:
        for symbol in PROXY_SYMBOLS:
            try:
                raw = fetch_finnhub_quote(symbol, api_key)
                parsed = parse_finnhub_quote(raw)
                if parsed is not None:
                    proxies[symbol] = parsed
            except Exception as e:  # noqa: BLE001
                errors.append({"source": f"proxy:{symbol}", "error": repr(e)})
                print(f"[memory] proxy {symbol} ERROR: {e}", file=sys.stderr)

    return {
        "asof": iso_utc_now(),
        "dram_spot": dram_spot,
        "nand_note": nand_note,
        "proxies": proxies,
        "errors": errors,
    }


def write(payload):
    atomic_write_json(latest_path("memory"), payload)
    append_history("memory", {
        "ts": payload["asof"],
        "dram_spot": payload.get("dram_spot", []),
    })


def main():
    payload = collect()
    write(payload)
    n_dram = len(payload["dram_spot"])
    n_err = len(payload["errors"])
    print(f"[memory] wrote {latest_path('memory')} ({n_dram} dram rows, {n_err} errors)")
    return 0 if n_dram > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
