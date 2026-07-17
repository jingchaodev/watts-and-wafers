import json
import os

import vast

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _load(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return f.read()


def test_parse_gpu_class_schema():
    raw = _load("vast_h100_sxm.json")
    result = vast.parse_gpu_class(raw)

    assert set(result.keys()) == {"offers", "total_gpus", "median_dph", "p25_dph", "min_dph"}
    assert isinstance(result["offers"], int)
    assert isinstance(result["total_gpus"], int)
    assert result["offers"] == 12
    # total_gpus = sum of num_gpus across all 12 offers
    assert result["total_gpus"] == sum(
        o["num_gpus"] for o in json.loads(raw)["offers"]
    )
    assert result["median_dph"] is not None
    assert result["min_dph"] is not None
    assert result["p25_dph"] is not None
    # min <= p25 <= median (per-GPU normalized dph)
    assert result["min_dph"] <= result["p25_dph"] <= result["median_dph"]


def test_parse_gpu_class_empty():
    raw = _load("vast_empty.json")
    result = vast.parse_gpu_class(raw)

    assert result["offers"] == 0
    assert result["total_gpus"] == 0
    assert result["median_dph"] is None
    assert result["p25_dph"] is None
    assert result["min_dph"] is None


def test_query_for_shape():
    q = vast._query_for("H100 SXM")
    assert q["gpu_name"] == {"eq": "H100 SXM"}
    assert q["rentable"] == {"eq": True}
    assert q["external"] == {"eq": False}
    assert q["limit"] == 300
