import os

import neoclouds

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


def test_parse_runpod_schema_and_null_handling():
    raw = _load("runpod_gputypes.json")
    result = neoclouds.parse_runpod(raw)

    assert isinstance(result, dict)
    # every value is a positive float
    for gpu, price in result.items():
        assert isinstance(price, float)
        assert price > 0

    # MI300X, B200, B300 have null prices in the fixture -> excluded, not crashed
    assert "MI300X" not in result
    assert "B200" not in result
    assert "B300" not in result

    # priced entries present with expected lowest values
    assert result["RTX 4090"] == 0.34
    assert result["L40S"] == 0.79
    assert result["H100"] == 2.69
    assert result["H200"] == 3.59
    # two A100 entries (PCIe 1.19, SXM 40GB 1.0 via bid fallback) -> lowest kept
    assert result["A100"] == 1.0


def test_parse_datacrunch_schema_and_on_demand_only():
    raw = _load("datacrunch_pricing.html")
    result = neoclouds.parse_datacrunch(raw)

    assert isinstance(result, dict)
    for gpu, price in result.items():
        assert isinstance(price, float)
        assert price > 0

    # fixture has on-demand, spot, cluster, and serverless variants per GPU;
    # only "on-demand" should ever be kept, and the lowest on-demand price wins
    assert result["H100"] == 3.25
    assert result["H200"] == 4.0
    assert result["B200"] == 6.11
    assert result["A100"] == 1.29  # 40GB on-demand beats 80GB on-demand
    assert result["L40S"] == 1.37  # plain on-demand beats serverless variants


def test_norm_gpu():
    assert neoclouds.norm_gpu("NVIDIA H100 80GB HBM3") == "H100"
    # "GB300" contains the "B300" substring -> normalizes to the B300 watch class
    assert neoclouds.norm_gpu("1x GB300 SXM6 288GB on-demand") == "B300"
    assert neoclouds.norm_gpu("unknown-thing") is None


def test_gpu_count_from_name():
    assert neoclouds.gpu_count_from_name("1x H100 SXM5 80GB on-demand") == 1
    assert neoclouds.gpu_count_from_name("16x H200 SXM5 141GB instant cluster") == 16
    assert neoclouds.gpu_count_from_name("no count here") == 1
