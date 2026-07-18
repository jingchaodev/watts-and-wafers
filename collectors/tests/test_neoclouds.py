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


def test_parse_lambda_schema_and_min_selection():
    raw = _load("lambda_pricing.html")
    result = neoclouds.parse_lambda(raw)

    assert isinstance(result, dict)
    for gpu, price in result.items():
        assert isinstance(price, float)
        assert price > 0

    # fixture has two "NVIDIA H100 SXM"/"NVIDIA H100 PCIe" rows -> both
    # normalize to H100, lowest (PCIe $3.29) wins over SXM $3.99
    assert result["H100"] == 3.29
    # fixture has two "NVIDIA A100 SXM" rows (80GB $2.79, 40GB $1.99) -> lowest kept
    assert result["A100"] == 1.99
    assert result["B200"] == 6.69
    assert result["GH200"] == 2.29
    # Tesla V100 isn't in WATCH_GPUS -> excluded, not crashed
    assert "V100" not in result
    assert len(result) == 4


def test_parse_nebius_schema_and_contact_us_skip():
    raw = _load("nebius_pricing.html")
    result = neoclouds.parse_nebius(raw)

    assert isinstance(result, dict)
    for gpu, price in result.items():
        assert isinstance(price, float)
        assert price > 0

    # on-demand (last cell), not preemptible (4th cell)
    assert result["H100"] == 3.85
    assert result["H200"] == 4.5
    assert result["B200"] == 7.15
    assert result["B300"] == 7.85
    assert result["L40S"] == 1.55  # "from $1.82" Intel row loses to "from $1.55" AMD row
    # GB300 NVL72 has "Contact us" instead of a $ price -> excluded, not crashed
    assert "GB200" not in result
    assert "GB300" not in result


def test_parse_crusoe_schema_and_contact_sales_skip():
    raw = _load("crusoe_pricing.html")
    result = neoclouds.parse_crusoe(raw)

    assert isinstance(result, dict)
    for gpu, price in result.items():
        assert isinstance(price, float)
        assert price > 0

    assert result["H200"] == 4.29
    assert result["H100"] == 3.9
    assert result["A100"] == 2.3
    assert result["L40S"] == 1.5
    assert result["MI300X"] == 3.45
    # GB200/B200/MI355X are "Contact sales" cards -> excluded, not crashed
    assert "GB200" not in result
    assert "B200" not in result
    assert "MI355X" not in result


def test_parse_coreweave_schema_and_per_node_division():
    raw = _load("coreweave_pricing.html")
    result = neoclouds.parse_coreweave(raw)

    assert isinstance(result, dict)
    for gpu, price in result.items():
        assert isinstance(price, float)
        assert price > 0

    # per-node price / gpu_count -> per-GPU price
    assert result["B200"] == 8.6      # $68.80 / 8
    assert result["H100"] == 6.155    # $49.24 / 8
    assert result["H200"] == 6.305    # $50.44 / 8
    assert result["A100"] == 2.7      # $21.60 / 8
    assert result["GH200"] == 6.5     # $6.50 / 1
    assert result["L40S"] == 2.25     # $18.00 / 8
    # GB200/GB300 NVL72 show an ambiguous "4^1" GPU-count footnote in this
    # fixture -> skipped (no safe division), not guessed
    assert "GB200" not in result
    assert "B300" not in result


def test_norm_gpu():
    assert neoclouds.norm_gpu("NVIDIA H100 80GB HBM3") == "H100"
    # "GB300" contains the "B300" substring -> normalizes to the B300 watch class
    assert neoclouds.norm_gpu("1x GB300 SXM6 288GB on-demand") == "B300"
    assert neoclouds.norm_gpu("unknown-thing") is None


def test_gpu_count_from_name():
    assert neoclouds.gpu_count_from_name("1x H100 SXM5 80GB on-demand") == 1
    assert neoclouds.gpu_count_from_name("16x H200 SXM5 141GB instant cluster") == 16
    assert neoclouds.gpu_count_from_name("no count here") == 1
