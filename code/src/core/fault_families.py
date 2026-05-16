"""Mapping from 10 AST-injection strategies → 5 paper-level fault families.

Paper Table tab:fault-family reports 5 families. This module is the canonical
source of truth for that rollup; recompute counts from
``data/tracebench_full.json`` and ``data/tracebench_hard.json`` rather than
trusting any stale numbers in earlier drafts.

Usage::

    from src.core.fault_families import family_of, family_counts

    family_of("boundary_condition_shift")   # → "boundary_off_by_one"
    counts = family_counts(entries)         # {family: total_count}
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, Iterable, List


# 10 strategies → 5 paper families. Source: src/core/ast_injector.py.
STRATEGY_TO_FAMILY: Dict[str, str] = {
    # Boundary / off-by-one
    "boundary_condition_shift": "boundary_off_by_one",
    "off_by_one": "boundary_off_by_one",
    "loop_entry_condition": "boundary_off_by_one",
    # Wrong operator / condition
    "wrong_operator": "wrong_op_cond",
    # Omission / missing branch
    "statement_omission": "omission_missing_branch",
    "missing_update_in_branch": "omission_missing_branch",
    # Dependency misuse
    "variable_shadowing": "dependency_misuse",
    "wrong_return_variable": "dependency_misuse",
    "arg_swap_call": "dependency_misuse",
    # Corner-case / type
    "initialization_error": "corner_case_type",
    "early_return_fallback": "corner_case_type",
    # The anchor_only strategy does not produce a semantic fault; if it ever
    # appears we route it to a sentinel family so it is not silently dropped.
    "anchor_only": "anchor_no_fault",
}

# Display names for paper tables.
FAMILY_DISPLAY: Dict[str, str] = {
    "boundary_off_by_one": "Boundary / off-by-one",
    "wrong_op_cond": "Wrong operator / condition",
    "omission_missing_branch": "Omission / missing branch",
    "dependency_misuse": "Dependency misuse",
    "corner_case_type": "Corner-case / type",
    "anchor_no_fault": "Anchor-only (no semantic fault)",
}

# Stable ordering for paper tables.
FAMILY_ORDER: List[str] = [
    "boundary_off_by_one",
    "wrong_op_cond",
    "omission_missing_branch",
    "dependency_misuse",
    "corner_case_type",
]


def family_of(strategy: str) -> str:
    """Return the family for an injection strategy, or 'unknown' if not mapped."""
    return STRATEGY_TO_FAMILY.get(strategy, "unknown")


def family_counts(entries: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """Aggregate injection counts by family across dataset entries.

    Each entry's ``injections`` is a list of dicts with at least a ``type``
    key. Strategies absent from STRATEGY_TO_FAMILY land in ``unknown``.
    """
    counter: Counter = Counter()
    for entry in entries:
        for inj in entry.get("injections", []) or []:
            counter[family_of(inj.get("type", ""))] += 1
    return dict(counter)


def family_counts_by_difficulty(
    entries: Iterable[Dict[str, Any]],
) -> Dict[str, Dict[str, int]]:
    """Aggregate injection counts by (family, difficulty_band).

    Returns ``{family: {band: count}}`` where band ∈ {easy_med, hard,
    very_hard_plus}. Entries with ``difficulty='unrated'`` are routed to
    ``easy_med`` (paper drops the 7 unrated problems).
    """
    band_map = {
        "easy": "easy_med",
        "medium": "easy_med",
        "hard": "hard",
        "very_hard": "very_hard_plus",
        "extreme": "very_hard_plus",
        "unrated": "easy_med",
    }
    result: Dict[str, Dict[str, int]] = {f: {"easy_med": 0, "hard": 0, "very_hard_plus": 0} for f in FAMILY_ORDER}
    for entry in entries:
        band = band_map.get(entry.get("difficulty", "unrated"), "easy_med")
        for inj in entry.get("injections", []) or []:
            fam = family_of(inj.get("type", ""))
            if fam in result:
                result[fam][band] += 1
    return result


def render_family_table(entries: Iterable[Dict[str, Any]]) -> str:
    """Render the paper-style family × difficulty table as a Markdown string."""
    counts = family_counts_by_difficulty(list(entries))
    rows = []
    rows.append("| Family | Easy-Med | Hard | VeryHard+ | Total |")
    rows.append("|--------|---------:|-----:|----------:|------:|")
    grand = {b: 0 for b in ("easy_med", "hard", "very_hard_plus")}
    for fam in FAMILY_ORDER:
        em, h, vh = counts[fam]["easy_med"], counts[fam]["hard"], counts[fam]["very_hard_plus"]
        total = em + h + vh
        rows.append(f"| {FAMILY_DISPLAY[fam]} | {em} | {h} | {vh} | {total} |")
        grand["easy_med"] += em
        grand["hard"] += h
        grand["very_hard_plus"] += vh
    grand_total = sum(grand.values())
    rows.append(f"| **Total** | **{grand['easy_med']}** | **{grand['hard']}** | **{grand['very_hard_plus']}** | **{grand_total}** |")
    return "\n".join(rows)


if __name__ == "__main__":  # pragma: no cover
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Compute fault-family table for a TraceBench split.")
    parser.add_argument("--input", required=True, help="Path to tracebench_full.json or tracebench_hard.json")
    args = parser.parse_args()
    with open(args.input, "r", encoding="utf-8") as fin:
        data = json.load(fin)
    print(render_family_table(data))
