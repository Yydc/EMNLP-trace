"""End-to-end integration test: load real dataset + reference trajectories,
run metrics, confirm no crashes and emit sensible values."""

import json
import os
import pytest
from pathlib import Path

DATA_DIR = Path("/Users/apple/Desktop/tracebench/data")


@pytest.fixture(scope="module")
def hard_split():
    p = DATA_DIR / "tracebench_hard.json"
    if not p.exists():
        pytest.skip(f"{p} missing — run from project root, or skip integration")
    return json.load(open(p))


def test_dataset_schema_invariants(hard_split):
    assert len(hard_split) == 128
    e = hard_split[0]
    assert e["multi_turn"] is True
    assert len(e["conversation_history"]) >= 1
    assert "injections" in e
    assert "rating" in e
    assert "difficulty" in e
    assert "depth" in e


def test_fault_family_rollup_total_matches_injections(hard_split):
    from src.core.fault_families import family_counts
    counts = family_counts(hard_split)
    total = sum(counts.values())
    inj_total = sum(e.get("meta_data", {}).get("num_injections", 0) for e in hard_split)
    assert total == inj_total, f"family count {total} ≠ inj total {inj_total}"


def test_difficulty_slicer_runs_with_synthetic_records(hard_split):
    """Inject 10 dummy per-problem records and check the slicer doesn't crash."""
    from src.evaluation.difficulty_slicer import slice_by_band

    by_id = {e["trace_id"]: e for e in hard_split}
    records = [
        {
            "trace_id": e["trace_id"],
            "solved": (i % 3 == 0),
            "blame_at_1": (i % 2),
            "outside_g": 0.4 if i % 2 else 0.1,
            "regression_rate": 0.2,
            "first_success_turn": (i % 5) + 1,
        }
        for i, e in enumerate(hard_split[:30])
    ]
    bands = slice_by_band(records, by_id)
    assert set(bands.keys()) >= {"easy_med", "hard", "very_hard_plus"}
    for b in ("easy_med", "hard", "very_hard_plus"):
        assert "n" in bands[b]


def test_failure_mode_classifier_handles_minimal_input():
    from src.evaluation.failure_modes import classify_trajectory
    log = {
        "turn_results": [{"attempts": [{
            "blame_spans": [{"start_line": 10, "end_line": 10}],
            "edited_lines": [10, 11],
        }]}],
    }
    rec = {"solved": True, "outside_g": 0.1, "regression_rate": 0.0}
    mode = classify_trajectory(log, rec, active_spans=[(10, 12)])
    assert mode == "precise_repair"


def test_bootstrap_ci_returns_three_floats():
    from src.evaluation.bootstrap import problem_bootstrap_ci
    point, lo, hi = problem_bootstrap_ci([0.1, 0.2, 0.3, 0.4, 0.5], n_resamples=200, seed=0)
    assert lo <= point <= hi


def test_aggregator_emits_v2_fields():
    """MetricAggregator.aggregate() must surface new metric keys."""
    from src.core.tracebench_eval import MetricAggregator
    agg = MetricAggregator(blame_k=[1, 3, 5], max_turns=5)
    # Empty aggregate is allowed; just confirm key presence.
    out = agg.aggregate()
    for k in ("outside_g", "regression_rate", "trajectory_slope_mean",
              "trajectory_r2_mean", "repeats_mean", "test_without_edit_mean",
              "per_problem_records"):
        assert k in out, f"missing aggregate key {k}"
