# Appendix plan

## A. Dataset card and release schema
- JSON schema for `tracebench_full.json` and `tracebench_hard.json`
- Fields: problem id, source metadata, verified reference, buggy program, tests, injected faults, active spans, counterfactual repair, transcript metadata
- License and release notes

## B. Construction details
- Reference program acquisition and validation
- AST parsing and dependency graph construction
- Fault injection operators
- Individual-failure and setwise-minimality checks
- Active-fault definition and tie-breaking

## C. Metric definitions
- Blame@1, Blame@k
- CF-Valid@1
- Outside-G and edit footprint alignment
- RegressionRate
- Accumulation slope and R^2
- Missing outputs and unparsable span handling

## D. Experimental protocol and cost accounting
- Models, backends, token budgets, turn budgets
- Sandbox/test timeouts
- Number of executions and average turns
- Total token usage / wall-clock accounting
- Statistical tests and bootstrap CIs

## E. Full results
- Full model table on TraceBench-Full
- Full model table on TraceBench-Hard
- Difficulty-bin breakdown
- Fault-family breakdown
- Outside-G vs RegressionRate regression
- Sensitivity to turn budget

## F. Case studies
- Precise localized repair
- Cascading semantic drift (main case)
- Feedback-guided recovery

## G. Optional trace-signal use case
- Place RAD/ARC-style steering here only as an illustration that trace signals are actionable
- Do not make it a main contribution
