import math

import pytest

from histra_builder.canonical import canonical_json_bytes, job_sha256, sha256_hex


def test_canonical_json_is_key_order_independent():
    left = {"b": 2, "a": {"y": 2, "x": 1}}
    right = {"a": {"x": 1, "y": 2}, "b": 2}
    assert canonical_json_bytes(left) == canonical_json_bytes(right)
    assert job_sha256(left) == job_sha256(right)


def test_canonical_json_rejects_non_finite_numbers():
    with pytest.raises(ValueError):
        canonical_json_bytes({"bad": math.nan})


def test_sha256_known_value():
    assert sha256_hex(b"abc") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
