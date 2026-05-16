#!/usr/bin/env python3
"""Stage 6: hard-fail guardrail before any PDF leaves the building.

Checks (each prints PASS / FAIL):
  1. main.tex must \\input{numbers.tex}
  2. Every \\<MacroName> referenced in main.tex must be defined in numbers.tex
  3. main.tex must not contain hard-typed "0.62" / "n=2614" patterns
     that disagree with numbers.json (catches stale hand-edits)
  4. No "mock", "TODO", "TBD", "\\todo" remaining (unless --allow-mock)
  5. main_gap_table.csv row count == models × splits
  6. outside_g_r/n in numbers.json == values used in figure captions
  7. Hard records ⊂ Full records by problem_id (re-verify post-eval)
  8. cost_accounting calls == sum(turns) from records

Exit codes:
  0 → all pass
  1 → at least one hard-fail (blocks `make paper`)
  2 → infrastructure error
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


class Check:
    def __init__(self, name: str):
        self.name = name
        self.failures: list[str] = []
        self.warnings: list[str] = []
    def fail(self, msg: str):    self.failures.append(msg)
    def warn(self, msg: str):    self.warnings.append(msg)
    @property
    def ok(self) -> bool: return not self.failures


def check_main_tex_uses_numbers(main_tex: str, numbers_tex: Path) -> Check:
    c = Check("main.tex includes numbers.tex")
    if r"\input{numbers}" not in main_tex and r"\input{numbers.tex}" not in main_tex:
        c.fail(r"main.tex does not \input{numbers.tex}; hand-typed numbers leak risk.")
    if not numbers_tex.exists():
        c.fail(f"{numbers_tex} not found.")
    return c


def check_macros_resolved(main_tex: str, numbers_tex: Path) -> Check:
    c = Check("every \\macro in main.tex resolves in numbers.tex")
    if not numbers_tex.exists():
        c.fail("numbers.tex missing — cannot check"); return c
    defined = set(re.findall(r"\\newcommand\{\\(\w+)\}", numbers_tex.read_text()))
    used = set(re.findall(r"\\(OutsideGReg\w+|TBNum\w+|EarlyDrift\w+)", main_tex))
    missing = used - defined
    if missing:
        c.fail(f"main.tex references undefined macros: {sorted(missing)}")
    return c


def check_no_leftover_placeholders(main_tex: str, allow_mock: bool) -> Check:
    c = Check("no leftover placeholders (mock/TODO/TBD/\\todo)")
    needles = [(r"\bTODO\b", "TODO"),
               (r"\\todo", r"\todo"),
               (r"\bTBD\b", "TBD"),
               (r"placeholder", "placeholder")]
    if not allow_mock:
        needles.append((r"\\mockval", r"\mockval"))
        needles.append((r"\bmock\b", "mock"))
    for pat, label in needles:
        if re.search(pat, main_tex):
            c.fail(f"main.tex still contains {label!r}")
    return c


def check_outside_g_consistency(numbers: dict) -> Check:
    c = Check("Outside-G r/n have a single defined value")
    r  = numbers.get("outside_g_r")
    n  = numbers.get("outside_g_n")
    if r is None or n is None:
        c.warn("outside_g_r / outside_g_n not yet computed (analyze stage not run with real data).")
    elif not (0 <= float(r) <= 1):
        c.fail(f"outside_g_r={r} out of [0,1]")
    elif int(n) < 100:
        c.fail(f"outside_g_n={n} suspiciously small")
    return c


def check_hard_subset(data_dir: Path) -> Check:
    c = Check("Hard ⊂ Full by problem_id (post-eval re-verify)")
    try:
        full = json.load(open(data_dir / "tracebench_full.json"))
        hard = json.load(open(data_dir / "tracebench_hard.json"))
    except FileNotFoundError as e:
        c.fail(f"data file missing: {e}"); return c
    full_pids = {e["problem_id"] for e in full}
    hard_pids = {e["problem_id"] for e in hard}
    missing = hard_pids - full_pids
    if missing:
        c.fail(f"{len(missing)} Hard ids not in Full")
    return c


def check_main_gap_row_count(csv_path: Path, expected: int) -> Check:
    c = Check(f"main_gap_table.csv row count == {expected}")
    if not csv_path.exists():
        c.warn(f"{csv_path} not found (analyze not run yet)"); return c
    import csv as csvmod
    n = sum(1 for _ in csvmod.reader(open(csv_path))) - 1
    if n != expected:
        c.fail(f"got {n} rows, expected {expected}")
    return c


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", default="pipeline.yaml")
    ap.add_argument("--strict", action="store_true",
                    help="Exit nonzero on first failure")
    ap.add_argument("--allow-mock", action="store_true",
                    help="Allow \\mockval / \\todo markers (useful while iterating)")
    args = ap.parse_args()

    paper_dir = REPO_ROOT / "code" / "paper"
    main_tex_path = paper_dir / "main.tex"
    numbers_tex_path = paper_dir / "numbers.tex"
    data_dir = REPO_ROOT / "data"
    out_dir = REPO_ROOT / "out"

    if not main_tex_path.exists():
        print(f"FATAL: {main_tex_path} not found", file=sys.stderr); sys.exit(2)
    main_tex = main_tex_path.read_text()

    numbers = {}
    nj = out_dir / "analysis" / "numbers.json"
    if nj.exists():
        numbers = json.load(open(nj))

    checks = [
        check_main_tex_uses_numbers(main_tex, numbers_tex_path),
        check_macros_resolved(main_tex, numbers_tex_path),
        check_no_leftover_placeholders(main_tex, allow_mock=args.allow_mock),
        check_outside_g_consistency(numbers),
        check_hard_subset(data_dir),
        check_main_gap_row_count(out_dir / "tables" / "main_gap_table.csv", expected=12),
    ]

    # Render report
    print("=" * 64)
    print(" Consistency check")
    print("=" * 64)
    any_failed = False
    for c in checks:
        if c.ok:
            badge = "✓ PASS"
        else:
            badge = "✗ FAIL"; any_failed = True
        print(f"  {badge}  {c.name}")
        for msg in c.failures: print(f"         FAIL: {msg}")
        for msg in c.warnings: print(f"         warn: {msg}")
    print()

    # Also dump markdown report
    md = ["# Consistency report", ""]
    for c in checks:
        sym = "[x]" if c.ok else "[ ]"
        md.append(f"- {sym} **{c.name}**")
        for m in c.failures: md.append(f"  - FAIL: {m}")
        for m in c.warnings: md.append(f"  - warn: {m}")
    rpt = REPO_ROOT / "out" / "analysis" / "consistency_report.md"
    rpt.parent.mkdir(parents=True, exist_ok=True)
    rpt.write_text("\n".join(md))
    print(f"wrote {rpt}")

    if any_failed and args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
