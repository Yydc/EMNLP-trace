"""Slice a Full-split evaluation into a Hard-split view.

Key fact (verified 2026-05-15): TraceBench-Hard is a strict subset of
TraceBench-Full by ``problem_id``. 128/128 Hard problem_ids overlap Full;
content (injections, turns, target_code) is identical for shared problem_ids.
The only wrinkle is that trace_id is renamed in Hard (``TB_HARD_00000`` ↔
``TB_00086`` in Full).

This module derives Hard rows from a single Full run, eliminating the need
for a separate Hard evaluation pass.

Public API::

    from src.evaluation.subset_slice import (
        slice_records_by_problem_ids,
        load_subset_problem_ids,
    )

    hard_pids = load_subset_problem_ids("data/tracebench_hard.json")
    hard_records = slice_records_by_problem_ids(full_records, hard_pids)
    # → identical fields, just filtered

The Full-run's per-problem records must carry a ``problem_id`` field for
the filter to work. ``MetricAggregator.add_result`` already records this
when the runner emits ``problem_id`` (= ``trace_id`` in the Full schema).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Set


def load_subset_problem_ids(subset_json_path: str | Path) -> Set[str]:
    """Read a TraceBench JSON file and return its set of ``problem_id`` values.

    Used to build the Hard-subset problem_id filter from
    ``data/tracebench_hard.json``.
    """
    path = Path(subset_json_path)
    if not path.exists():
        raise FileNotFoundError(f"subset file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    pids = set()
    for entry in data:
        pid = entry.get("problem_id")
        if pid:
            pids.add(pid)
    return pids


def slice_records_by_problem_ids(
    full_records: Iterable[Dict[str, Any]],
    subset_problem_ids: Set[str],
) -> List[Dict[str, Any]]:
    """Filter per-problem records to those whose ``problem_id`` is in the subset.

    Field-preserving: returns the same record objects, just filtered. Order
    is preserved.
    """
    if not subset_problem_ids:
        return []
    return [r for r in full_records if r.get("problem_id") in subset_problem_ids]


def derive_hard_from_full(
    full_records_path: str | Path,
    hard_dataset_path: str | Path = "data/tracebench_hard.json",
    output_path: str | Path | None = None,
) -> List[Dict[str, Any]]:
    """End-to-end convenience: load a Full run's per-problem records (jsonl)
    and write Hard's derived records.

    Args:
      full_records_path: jsonl file from a Full evaluation run.
      hard_dataset_path: path to ``data/tracebench_hard.json`` (the subset
                         membership source).
      output_path: optional jsonl path to write Hard records.

    Returns:
      The derived list (also written to ``output_path`` if given).
    """
    pids = load_subset_problem_ids(hard_dataset_path)
    full_records = []
    with open(full_records_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                full_records.append(json.loads(line))

    hard_records = slice_records_by_problem_ids(full_records, pids)

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            for r in hard_records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    return hard_records


def main() -> None:  # pragma: no cover
    import argparse
    p = argparse.ArgumentParser(description="Derive Hard records from a Full evaluation run.")
    p.add_argument("--full-records", required=True, help="Path to Full jsonl per-problem records")
    p.add_argument("--hard-dataset", default="data/tracebench_hard.json")
    p.add_argument("--output", required=True, help="Where to write the Hard jsonl records")
    args = p.parse_args()
    n = derive_hard_from_full(args.full_records, args.hard_dataset, args.output)
    print(f"wrote {len(n)} hard records to {args.output}")


if __name__ == "__main__":
    main()
