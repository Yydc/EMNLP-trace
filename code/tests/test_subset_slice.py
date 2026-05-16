"""Tests for the Hard-subset-from-Full slicer.

The slicer's correctness depends on Hard being a strict subset of Full by
problem_id (verified 2026-05-15: 128/128 overlap).
"""
import json
from pathlib import Path

import pytest

from src.evaluation.subset_slice import (
    load_subset_problem_ids,
    slice_records_by_problem_ids,
    derive_hard_from_full,
)


DATA_DIR = Path("/Users/apple/Desktop/tracebench/data")


@pytest.fixture(scope="module")
def hard_pids():
    p = DATA_DIR / "tracebench_hard.json"
    if not p.exists():
        pytest.skip(f"{p} missing")
    return load_subset_problem_ids(p)


def test_load_subset_problem_ids_returns_set(hard_pids):
    assert isinstance(hard_pids, set)
    assert len(hard_pids) == 128


def test_all_hard_pids_present_in_full(hard_pids):
    """The whole point: every Hard problem_id must exist in Full."""
    full_pids = load_subset_problem_ids(DATA_DIR / "tracebench_full.json")
    assert hard_pids.issubset(full_pids), \
        f"{len(hard_pids - full_pids)} Hard problems missing from Full"


def test_slice_records_filters_by_problem_id():
    records = [
        {"problem_id": "A", "value": 1},
        {"problem_id": "B", "value": 2},
        {"problem_id": "C", "value": 3},
    ]
    out = slice_records_by_problem_ids(records, {"A", "C"})
    assert len(out) == 2
    assert {r["problem_id"] for r in out} == {"A", "C"}


def test_slice_records_preserves_field_objects():
    records = [{"problem_id": "X", "nested": {"k": "v"}, "list": [1, 2, 3]}]
    out = slice_records_by_problem_ids(records, {"X"})
    assert out[0] is records[0]  # same object reference, no copy


def test_slice_records_empty_subset_returns_empty_list():
    assert slice_records_by_problem_ids([{"problem_id": "A"}], set()) == []


def test_slice_records_missing_problem_id_field_silently_drops():
    records = [{"problem_id": "A"}, {"other_field": "no_pid"}]
    out = slice_records_by_problem_ids(records, {"A"})
    assert len(out) == 1


def test_slice_records_preserves_order():
    records = [{"problem_id": f"P{i}", "i": i} for i in range(10)]
    keep = {"P3", "P1", "P7"}
    out = slice_records_by_problem_ids(records, keep)
    # Should be in the original order, not subset-iteration order
    assert [r["problem_id"] for r in out] == ["P1", "P3", "P7"]


def test_derive_hard_from_full_end_to_end(tmp_path, hard_pids):
    """Write a fake Full jsonl, run derive, check Hard count."""
    full_jsonl = tmp_path / "full.jsonl"
    with full_jsonl.open("w") as fh:
        # Write 100 records: 50 in Hard, 50 not
        in_hard = list(hard_pids)[:50]
        for pid in in_hard:
            fh.write(json.dumps({"problem_id": pid, "solved": True, "blame_at_1": 1}) + "\n")
        for i in range(50):
            fh.write(json.dumps({"problem_id": f"NOT_HARD_{i}", "solved": False, "blame_at_1": 0}) + "\n")

    out_jsonl = tmp_path / "hard.jsonl"
    derived = derive_hard_from_full(
        full_records_path=str(full_jsonl),
        hard_dataset_path=str(DATA_DIR / "tracebench_hard.json"),
        output_path=str(out_jsonl),
    )
    assert len(derived) == 50

    # Verify the output file exists and has right line count
    written = out_jsonl.read_text().splitlines()
    assert len(written) == 50
