#!/usr/bin/env python3
"""Azure hyperscaler collector — ND-series GPU SKU pricing (daily).

Queries the Azure Retail Prices API for Virtual Machines SKUs whose
armSkuName contains "ND" (the GPU-accelerated family: NDxxx H100/H200/GB200),
follows NextPageLink pagination (capped), then for each SKU keeps the
cheapest US-region on-demand ('Consumption', Linux, not Low Priority) price
plus its spot variant if published. Writes data/latest/hyperscaler.json per
docs/DATA_CONTRACT.md.
"""
import re
import sys
from urllib.parse import quote

from common import atomic_write_json, append_history, fetch_url, iso_utc_now, latest_path

PRICES_URL = "https://prices.azure.com/api/retail/prices"
FILTER = "serviceName eq 'Virtual Machines' and contains(armSkuName,'ND')"
MAX_PAGES = 10

# US regions only, preferring the classic public-cloud names.
US_REGIONS = {
    "eastus", "eastus2", "westus", "westus2", "westus3", "centralus",
    "northcentralus", "southcentralus", "westcentralus",
}

# armSkuName regex -> (canonical gpu name, gpus_per_vm). ND96* families are 8
# GPUs/VM; the GB200 NDv6 family (ND128isr[f]_NDR_GB200_v6) ships 4 GB200
# superchips (8 GPU dies, but Azure prices/allocates at the 4-superchip
# granularity for this SKU family) — we keep it conservative and explicit
# rather than guessing per vCPU count.
SKU_FAMILIES = (
    (re.compile(r"ND\d+\w*_H200", re.I), "H200", 8),
    (re.compile(r"ND\d+\w*_H100", re.I), "H100", 8),
    (re.compile(r"ND\d+\w*GB200", re.I), "GB200", 4),
    (re.compile(r"ND\d+\w*_A100", re.I), "A100", 8),
)


def gpu_for_sku(sku):
    for rx, gpu, cnt in SKU_FAMILIES:
        if rx.search(sku):
            return gpu, cnt
    return None, None


def _is_on_demand_row(item):
    """True if this Items[] row is a plain US on-demand (not spot/reservation/
    Windows/low-priority/dev-test) rate."""
    if item.get("type") != "Consumption":
        return False
    sku_name = (item.get("skuName") or "")
    product_name = (item.get("productName") or "")
    if "spot" in sku_name.lower():
        return False
    if "windows" in product_name.lower():
        return False
    if "low priority" in sku_name.lower() or "lowpriority" in sku_name.lower():
        return False
    if item.get("armRegionName") not in US_REGIONS:
        return False
    return True


def _is_spot_row(item):
    if item.get("type") != "Consumption":
        return False
    sku_name = (item.get("skuName") or "")
    product_name = (item.get("productName") or "")
    if "spot" not in sku_name.lower():
        return False
    if "windows" in product_name.lower():
        return False
    if item.get("armRegionName") not in US_REGIONS:
        return False
    return True


def fetch_all_pages(timeout=25, retries=2, max_pages=MAX_PAGES):
    """Fetch every page (capped) and return list of raw JSON text bodies."""
    pages = []
    url = PRICES_URL + "?$filter=" + quote(FILTER)
    for _ in range(max_pages):
        raw = fetch_url(url, timeout=timeout, retries=retries)
        pages.append(raw)
        import json
        doc = json.loads(raw)
        nxt = doc.get("NextPageLink")
        if not nxt:
            break
        url = nxt
    return pages


def parse_pages(raw_json_texts):
    """Pure parse: list of raw page bodies -> contract's azure dict.

    For each SKU we recognize, pick the cheapest US on-demand row (min
    retailPrice across regions) and its cheapest US spot row if any.
    """
    import json

    best_ondemand = {}  # sku -> item
    best_spot = {}  # sku -> item

    for raw in raw_json_texts:
        doc = json.loads(raw)
        for item in doc.get("Items", []):
            sku = item.get("armSkuName") or ""
            gpu, gpus_per_vm = gpu_for_sku(sku)
            if not gpu:
                continue
            price = item.get("retailPrice")
            if price is None:
                continue
            if _is_on_demand_row(item):
                cur = best_ondemand.get(sku)
                if cur is None or price < cur["retailPrice"]:
                    best_ondemand[sku] = item
            elif _is_spot_row(item):
                cur = best_spot.get(sku)
                if cur is None or price < cur["retailPrice"]:
                    best_spot[sku] = item

    azure = {}
    for sku, item in best_ondemand.items():
        gpu, gpus_per_vm = gpu_for_sku(sku)
        vm_hr = float(item["retailPrice"])
        spot_item = best_spot.get(sku)
        spot_vm_hr = float(spot_item["retailPrice"]) if spot_item else None
        azure[sku] = {
            "gpu": gpu,
            "gpus_per_vm": gpus_per_vm,
            "ondemand_vm_hr": round(vm_hr, 4),
            "spot_vm_hr": round(spot_vm_hr, 4) if spot_vm_hr is not None else None,
            "ondemand_gpu_hr": round(vm_hr / gpus_per_vm, 4),
            "region": item.get("armRegionName"),
        }
    return azure


def collect():
    errors = []
    azure = {}
    try:
        pages = fetch_all_pages()
        azure = parse_pages(pages)
    except Exception as e:  # noqa: BLE001
        errors.append({"source": "azure_retail_prices", "error": repr(e)})
        print(f"[hyperscaler] azure ERROR: {e}", file=sys.stderr)
    return {"asof": iso_utc_now(), "azure": azure, "errors": errors}


def write(payload):
    atomic_write_json(latest_path("hyperscaler"), payload)
    append_history("hyperscaler", {"ts": payload["asof"], "azure": payload.get("azure", {})})


def main():
    payload = collect()
    write(payload)
    n_ok = len(payload["azure"])
    n_err = len(payload["errors"])
    print(f"[hyperscaler] wrote {latest_path('hyperscaler')} ({n_ok} SKUs ok, {n_err} errors)")
    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
