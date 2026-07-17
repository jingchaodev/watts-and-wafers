import json
import os

import hyperscaler

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_pages():
    with open(os.path.join(FIXTURES, "azure_pages.json")) as f:
        pages = json.load(f)
    # fixture stores parsed page dicts; parse_pages() expects raw JSON text
    return [json.dumps(p) for p in pages]


def test_parse_pages_schema():
    raw_pages = _load_pages()
    azure = hyperscaler.parse_pages(raw_pages)

    assert isinstance(azure, dict)
    assert len(azure) > 0

    for sku, entry in azure.items():
        assert set(entry.keys()) == {
            "gpu", "gpus_per_vm", "ondemand_vm_hr", "spot_vm_hr",
            "ondemand_gpu_hr", "region",
        }
        assert entry["gpu"] in ("H100", "H200", "GB200", "A100")
        assert isinstance(entry["gpus_per_vm"], int) and entry["gpus_per_vm"] > 0
        assert isinstance(entry["ondemand_vm_hr"], float) and entry["ondemand_vm_hr"] > 0
        assert entry["spot_vm_hr"] is None or (
            isinstance(entry["spot_vm_hr"], float) and entry["spot_vm_hr"] > 0
        )
        # ondemand_gpu_hr = ondemand_vm_hr / gpus_per_vm
        expected = round(entry["ondemand_vm_hr"] / entry["gpus_per_vm"], 4)
        assert entry["ondemand_gpu_hr"] == expected
        assert entry["region"] in hyperscaler.US_REGIONS


def test_gpu_for_sku():
    assert hyperscaler.gpu_for_sku("Standard_ND96isr_H100_v5") == ("H100", 8)
    assert hyperscaler.gpu_for_sku("Standard_ND96isr_H200_v5") == ("H200", 8)
    assert hyperscaler.gpu_for_sku("Standard_ND128isr_NDR_GB200_v6") == ("GB200", 4)
    assert hyperscaler.gpu_for_sku("Standard_ND96ams_A100_v4") == ("A100", 8)
    assert hyperscaler.gpu_for_sku("Standard_D2s_v3") == (None, None)


def test_row_filters():
    on_demand = {
        "type": "Consumption", "skuName": "ND96isr H100 v5",
        "productName": "Virtual Machines NDsr H100 v5 Series Linux",
        "armRegionName": "eastus",
    }
    spot = {
        "type": "Consumption", "skuName": "ND96isr H100 v5 Spot",
        "productName": "Virtual Machines NDsr H100 v5 Series Linux",
        "armRegionName": "eastus",
    }
    windows = {
        "type": "Consumption", "skuName": "ND96isr H100 v5",
        "productName": "Virtual Machines NDsr H100 v5 Series Windows",
        "armRegionName": "eastus",
    }
    non_us = dict(on_demand, armRegionName="switzerlandwest")

    assert hyperscaler._is_on_demand_row(on_demand) is True
    assert hyperscaler._is_on_demand_row(spot) is False
    assert hyperscaler._is_on_demand_row(windows) is False
    assert hyperscaler._is_on_demand_row(non_us) is False

    assert hyperscaler._is_spot_row(spot) is True
    assert hyperscaler._is_spot_row(on_demand) is False
