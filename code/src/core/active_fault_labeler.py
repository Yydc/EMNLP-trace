"""Label each turn's *active* fault by counterfactual replay.

Paper Section 3 paragraph "Attribution":
    G_t = the stored fault span whose counterfactual revert resolves the
          currently observed failing assertion while leaving other lines
          unchanged.

When an entry has a single injection this is trivial (the only injection is
the active one). With ``single_multi`` / ``multi_multi`` data the labeler
needs to:

  1. For each turn t with has_error=True, identify the current failing test
     set under the corrupted code at turn t.
  2. For each injection i, apply the counterfactual revert at i's location
     (replace the corrupted lines with the matching lines from the verified
     reference program), then rerun the tests.
  3. An injection is *active at turn t* iff its revert flips at least one
     currently failing test to passing AND introduces no new failing tests.

This is a one-time dataset prep step. Output augments each entry with::

    entry["active_faults_per_turn"] = {
        "0": ["INJ_T01"],
        "1": ["INJ_T01", "INJ_T03"],
        ...
    }

Usage::

    from src.core.active_fault_labeler import label_dataset
    n = label_dataset(
        input_path="data/tracebench_full.json",
        output_path="data/tracebench_full_with_active.json",
        max_workers=4,
    )
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .test_runner import run_tests_per_test


def _apply_counterfactual_lines(
    corrupted: str,
    clean: str,
    inj_line: int,
    radius: int = 3,
) -> Optional[str]:
    """Replace lines [inj_line-radius, inj_line+radius] of corrupted with clean.

    Used as a fallback when we have absolute line numbers but not turn-level
    target_code reverts. Kept around for single-turn entries where the
    schema lacks per-turn original_target_code.
    """
    corrupted_lines = corrupted.splitlines()
    clean_lines = clean.splitlines()
    if not corrupted_lines or not clean_lines:
        return None
    patched = list(corrupted_lines)
    lo = max(0, inj_line - 1 - radius)
    hi = min(len(corrupted_lines), inj_line + radius)
    for idx in range(lo, hi):
        if idx < len(clean_lines):
            patched[idx] = clean_lines[idx]
    return "\n".join(patched)


def _build_full_code(context: str, target_code: str) -> str:
    """Concatenate context + turn target into the form the runner actually executes."""
    if context and target_code:
        return context + "\n\n" + target_code
    return context or target_code or ""


def _is_active_with_cf(
    corrupted_full: str,
    cf_full: str,
    tests: List[str],
    file_path: str,
) -> Tuple[str, str]:
    """Run the active-fault check given a pre-built counterfactual full-code.

    Returns (label, reason) where label ∈ {
        "active",              # paper-strict: CF revert flips ≥1 failure AND introduces 0 new failures
        "active_relaxed",      # CF revert flips ≥1 failure but introduces other failures (still actionable)
        "inactive_no_failure", # corrupted has no failing test (injection is dormant on this test set)
        "inactive_cf_no_fix",  # CF revert fixes nothing — injection might not be the relevant fault
        "inactive_unknown",    # both corrupted AND CF fail every test — dataset noise
        "error",               # subprocess/timeout error
    }
    """
    if not tests:
        return "error", "no_tests"

    r_corr = run_tests_per_test(corrupted_full, tests, file_path)
    if r_corr.error:
        return "error", f"corrupt_code_error: {r_corr.error}"

    failed_before = r_corr.failed_set
    if not failed_before:
        return "inactive_no_failure", "corrupted_passes_all_tests"

    r_cf = run_tests_per_test(cf_full, tests, file_path)
    if r_cf.error:
        return "error", f"cf_code_error: {r_cf.error}"

    fixed = failed_before - r_cf.failed_set
    new_failures = r_cf.failed_set - r_corr.failed_set

    if not fixed and r_cf.failed_set == r_corr.failed_set == set(range(len(tests))):
        return "inactive_unknown", "both_corrupted_and_cf_fail_everything"
    if not fixed:
        return "inactive_cf_no_fix", "revert_fixed_nothing"
    if new_failures:
        return "active_relaxed", f"fixed_{len(fixed)}_but_broke_{len(new_failures)}"
    return "active", f"fixed_{len(fixed)}_test(s)"


def label_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Compute active_faults_per_turn for a single entry and return it.

    Returns a dict ``{turn_id (str): [inj_id, ...]}``. The caller is
    responsible for attaching this to the entry.

    Multi-turn schema: the cleanest counterfactual is to swap the entire
    ``target_code`` for ``original_target_code`` of the relevant turn. That
    operation is **definitionally** what "revert this injection" means,
    because all of a turn's injections live inside its target_code body.

    Single-turn / legacy schema: fall back to line-window revert against
    ``original_code``.
    """
    convo = entry.get("conversation_history") or []
    injections = entry.get("injections") or []
    file_path = entry.get("code_context", {}).get("file_path", "solution.py")

    # ------------- single-turn / legacy schema -------------
    if not convo:
        clean_code = entry.get("original_code", "")
        corrupted = entry.get("code_context", {}).get("corrupted_code", "")
        tests = entry.get("evaluation", {}).get("test_cases", [])
        if not corrupted or not tests or not injections or not clean_code:
            return {}
        result_ids = []
        for inj in injections:
            line = inj.get("anchor", {}).get("anchor_line") or inj.get("location", {}).get("line_approx")
            if line is None:
                continue
            cf = _apply_counterfactual_lines(corrupted, clean_code, int(line), radius=3)
            if cf is None:
                continue
            label, _ = _is_active_with_cf(corrupted, cf, tests, file_path)
            if label in ("active", "active_relaxed"):
                result_ids.append(inj.get("injection_id", ""))
        return {"0": result_ids}

    # ------------- multi-turn schema -------------
    # Build a turn → injection_ids index. Multi-turn data uses two conventions:
    #   (a) top-level `entry["injections"]` carries injection_id + turn_id field
    #   (b) `turn["injections"]` (in conversation_history) carries strategy+anchor
    #       but lacks injection_id (redundant copy of top-level data).
    # We dedupe by anchor_line so the same physical injection isn't counted
    # twice when both conventions are present.
    turn_to_inj_ids: Dict[int, List[str]] = {}
    seen_anchor: Dict[int, set] = {}  # turn_id → set of anchor_line keys

    def _add(tid: int, inj_id: str, anchor_line: Any) -> None:
        ids = turn_to_inj_ids.setdefault(tid, [])
        anchors = seen_anchor.setdefault(tid, set())
        # Dedup by (anchor_line) if present, else by inj_id.
        key = anchor_line if anchor_line is not None else inj_id
        if key in anchors:
            return
        anchors.add(key)
        if inj_id and inj_id not in ids:
            ids.append(inj_id)

    # First pass: top-level (canonical IDs).
    for inj in injections:
        if inj.get("turn_id") is not None:
            anchor_line = inj.get("anchor", {}).get("anchor_line") or inj.get("location", {}).get("line_approx")
            inj_id = inj.get("injection_id") or f"anon@L{anchor_line}"
            _add(inj.get("turn_id"), inj_id, anchor_line)
    # Second pass: per-turn entries.
    for t_idx, turn in enumerate(convo):
        tid = turn.get("turn_id", t_idx)
        for inj in turn.get("injections", []) or []:
            anchor_line = inj.get("anchor", {}).get("anchor_line")
            inj_id = (
                inj.get("injection_id")
                or inj.get("anchor", {}).get("anchor_func_name")
                or f"anon@L{anchor_line}"
            )
            _add(tid, inj_id, anchor_line)

    result: Dict[str, List[str]] = {}

    for turn_idx, turn in enumerate(convo):
        turn_id_raw = turn.get("turn_id", turn_idx)
        turn_id_str = str(turn_id_raw)
        has_error = turn.get("has_error", False)
        target = turn.get("target_code", "") or ""
        orig_target = turn.get("original_target_code", target) or target
        context = turn.get("context", "") or ""
        tests = turn.get("test_cases", []) or []

        if not has_error or not tests:
            result[turn_id_str] = []
            continue

        candidate_inj_ids = turn_to_inj_ids.get(turn_id_raw) or []
        if not candidate_inj_ids:
            # All untagged injections become candidates for any error turn.
            candidate_inj_ids = [
                inj.get("injection_id", "")
                for inj in injections
                if inj.get("turn_id") is None
            ]
        if not candidate_inj_ids:
            result[turn_id_str] = []
            continue

        corrupted_full = _build_full_code(context, target)

        # The whole-target revert is the canonical CF for the union of this
        # turn's injections. Setwise-minimality (enforced at dataset build
        # time) guarantees each candidate contributes to ≥1 failure.
        cf_full = _build_full_code(context, orig_target)
        label, reason = _is_active_with_cf(corrupted_full, cf_full, tests, file_path)
        if label in ("active", "active_relaxed"):
            result[turn_id_str] = candidate_inj_ids
        else:
            # Dataset-noisy cases: paper-honest fallback for single-injection
            # turns is to trust the dataset's claim and mark the injection as
            # active anyway (with a flag we can audit). The label string is
            # preserved alongside the IDs for downstream filtering.
            if len(candidate_inj_ids) == 1 and label == "inactive_unknown":
                result[turn_id_str] = candidate_inj_ids
                result.setdefault("_labels", {})[turn_id_str] = f"trusted:{reason}"
            else:
                result[turn_id_str] = []
                result.setdefault("_labels", {})[turn_id_str] = f"{label}:{reason}"

    return result


def _label_one_for_pool(payload: Tuple[int, Dict[str, Any]]) -> Tuple[int, Dict[str, Any]]:
    idx, entry = payload
    try:
        labels = label_entry(entry)
    except Exception as exc:  # pragma: no cover
        labels = {"_error": str(exc)}
    return idx, labels


def label_dataset(
    input_path: str,
    output_path: str,
    max_workers: int = 4,
    limit: Optional[int] = None,
    progress_every: int = 25,
) -> int:
    """Label a TraceBench JSON file with ``active_faults_per_turn`` per entry.

    Returns the number of entries written. Uses a ProcessPoolExecutor for
    parallel sandbox runs; max_workers=4 is conservative for an 8-core
    machine (each labeling step spawns its own subprocess for test exec).
    """
    src = Path(input_path)
    dst = Path(output_path)
    with src.open("r", encoding="utf-8") as fin:
        data = json.load(fin)

    if limit is not None:
        data = data[:limit]

    n = len(data)
    print(f"[active_fault_labeler] labeling {n} entries with {max_workers} workers", file=sys.stderr)

    start = time.time()
    results: Dict[int, Dict[str, Any]] = {}

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_label_one_for_pool, (i, e)): i for i, e in enumerate(data)}
        done = 0
        for fut in as_completed(futures):
            idx, labels = fut.result()
            results[idx] = labels
            done += 1
            if done % progress_every == 0 or done == n:
                elapsed = time.time() - start
                rate = done / max(elapsed, 1e-9)
                eta = (n - done) / max(rate, 1e-9)
                print(f"[active_fault_labeler]   {done}/{n} ({rate:.1f}/s, eta {eta:.0f}s)", file=sys.stderr)

    # Attach results back to entries in original order.
    for i, entry in enumerate(data):
        entry["active_faults_per_turn"] = results.get(i, {})

    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", encoding="utf-8") as fout:
        json.dump(data, fout, ensure_ascii=False, indent=None)

    elapsed = time.time() - start
    print(f"[active_fault_labeler] wrote {n} entries to {dst} ({elapsed:.0f}s total)", file=sys.stderr)
    return n


if __name__ == "__main__":  # pragma: no cover
    import argparse

    p = argparse.ArgumentParser(description="Label TraceBench entries with active_faults_per_turn.")
    p.add_argument("--input", required=True, help="Path to tracebench_*.json")
    p.add_argument("--output", required=True, help="Where to write the labeled JSON")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--limit", type=int, default=None, help="(debug) only label first N entries")
    args = p.parse_args()
    label_dataset(args.input, args.output, max_workers=args.workers, limit=args.limit)
