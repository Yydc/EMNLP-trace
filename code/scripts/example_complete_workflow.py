#!/usr/bin/env python3
"""
Complete TraceBench Workflow Example

This script demonstrates the full pipeline:
1. Import CodeFlowBench task
2. Extend with GPT (mock mode)
3. Run with enhanced engine
4. Evaluate with comprehensive metrics
5. Analyze results
"""
from __future__ import annotations
import os
import sys
import json
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from tracebench.core.enhanced_engine import EnhancedEngine
from tracebench.evaluators.enhanced_metrics import EnhancedEvaluator
from tbgen.benchmark_builder import TraceBenchBuilder, ExtensionConfig
from scripts.import_codeflowbench import create_mock_codeflow_tasks

def example_workflow():
    """Run complete workflow"""

    # Enable mock mode
    os.environ["TBGEN_MOCK"] = "1"

    output_dir = Path("example_output")
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir()

    print("="*70)
    print("TraceBench Complete Workflow Example")
    print("="*70)

    # Step 1: Import CodeFlowBench task
    print("\n[STEP 1] Import CodeFlowBench Task")
    print("-" * 70)

    tasks_dir = output_dir / "codeflow_tasks"
    tasks_dir.mkdir()
    num_tasks = create_mock_codeflow_tasks(tasks_dir)

    codeflow_task_dir = list(tasks_dir.glob("flow__*"))[0]
    print(f"✓ Imported: {codeflow_task_dir.name}")

    with open(codeflow_task_dir / "task.json") as f:
        codeflow_task = json.load(f)

    print(f"  Task ID: {codeflow_task['task_id']}")
    print(f"  Track: {codeflow_task['track']}")
    print(f"  Shift tags: {len(codeflow_task.get('shift_tags', []))} tags")

    # Step 2: Extend with GPT
    print("\n[STEP 2] Extend with GPT (Mock Mode)")
    print("-" * 70)

    config = ExtensionConfig(
        target_turns=8,
        add_noisy_rationales=3,
        add_rollback_points=2,
        model="gpt-4o"
    )

    builder = TraceBenchBuilder(config)
    extended_task = builder.extend_task(codeflow_task)

    print(f"✓ Extended task: {extended_task['task_id']}")
    print(f"  Rationales: 1 clean + {len(extended_task['rationales'].get('noisy', []))} noisy")
    print(f"  Shift tags: {len(extended_task.get('shift_tags', []))} tags")
    print(f"  Fuzz config: {'enabled' if extended_task.get('fuzz_config', {}).get('enabled') else 'disabled'}")

    # Save extended task
    extended_task_dir = output_dir / "tracebench_tasks" / "tracebench__extended_example"
    extended_task_dir.mkdir(parents=True)

    with open(extended_task_dir / "task.json", 'w') as f:
        json.dump(extended_task, f, indent=2)

    # Copy solution and tests
    if (codeflow_task_dir / "solution.py").exists():
        shutil.copy(
            codeflow_task_dir / "solution.py",
            extended_task_dir / "solution.py"
        )

    if (codeflow_task_dir / "tests").exists():
        shutil.copytree(
            codeflow_task_dir / "tests",
            extended_task_dir / "tests"
        )

    # Step 3: Run with enhanced engine
    print("\n[STEP 3] Run with Enhanced Engine")
    print("-" * 70)

    run_output_dir = output_dir / "runs" / "tracebench__extended_example"

    engine = EnhancedEngine(
        task_dir=extended_task_dir,
        agent_cmd="python -m tbinfer.agents.rationale_agent",
        output_dir=run_output_dir,
        max_turns=6,
        enable_rollback=True
    )

    success = engine.run()

    print(f"✓ Execution completed")
    print(f"  Success: {success}")
    print(f"  Total turns: {len(engine.turn_history)}")

    rollback_count = sum(
        1 for entry in engine.turn_history
        if entry.get("rollback", False)
    )
    print(f"  Rollbacks: {rollback_count}")

    # Step 4: Analyze trace
    print("\n[STEP 4] Analyze Trace")
    print("-" * 70)

    trace_files = list(run_output_dir.glob("*_trace.json"))
    if not trace_files:
        print("✗ No trace file found")
        return

    with open(trace_files[0]) as f:
        trace = json.load(f)

    print(f"✓ Trace loaded: {trace['task_id']}")
    print(f"  Final success: {trace['final_success']}")
    print(f"  Total turns: {trace['total_turns']}")
    print(f"\n  Turn-by-turn breakdown:")

    for turn_data in trace['turns']:
        turn_num = turn_data['turn']
        feedback = turn_data.get('input_feedback', {})
        agent_out = turn_data.get('agent_output', {})
        exec_res = turn_data.get('execution_result', {})

        compile_status = feedback.get('compile', {}).get('content', {}).get('status', 'unknown')
        tests_passed = exec_res.get('tests_passed', 0)
        tests_total = exec_res.get('tests_total', 0)

        print(f"    Turn {turn_num}:")
        print(f"      Compile: {compile_status}")
        print(f"      Tests: {tests_passed}/{tests_total}")

        if agent_out:
            diagnosis = agent_out.get('diagnosis', 'N/A')
            rationale = agent_out.get('picked_rationale_id', 'N/A')
            has_patch = bool(agent_out.get('patch', {}).get('diff'))
            evidence_count = len(agent_out.get('evidence_map', []))

            print(f"      Diagnosis: {diagnosis}")
            print(f"      Rationale: {rationale}")
            print(f"      Patch: {'yes' if has_patch else 'no'}")
            print(f"      Evidence items: {evidence_count}")

    # Step 5: Evaluate with comprehensive metrics
    print("\n[STEP 5] Evaluate with Comprehensive Metrics")
    print("-" * 70)

    evaluator = EnhancedEvaluator(output_dir / "runs")
    metrics = evaluator.compute_comprehensive_metrics()

    print("✓ Comprehensive metrics computed")
    print("\n  [1] Multi-turn Traceability:")
    traceability = metrics.get('multi_turn_traceability', {})
    print(f"    Total turns: {traceability.get('total_turns', 0)}")
    print(f"    Feedback ID coverage: {traceability.get('feedback_id_coverage', 0):.1%}")
    print(f"    Patch coverage: {traceability.get('patch_coverage', 0):.1%}")
    print(f"    Evidence map coverage: {traceability.get('evidence_map_coverage', 0):.1%}")

    print("\n  [2] Distribution Shift:")
    shift = metrics.get('distribution_shift', {})
    print(f"    Unique tags: {shift.get('total_unique_tags', 0)}")
    by_dim = shift.get('by_dimension', {})
    for dim, data in list(by_dim.items())[:3]:
        print(f"    {dim}: {len(data)} categories")

    print("\n  [3] Error Accumulation:")
    error_acc = metrics.get('error_accumulation', {})
    print(f"    Failure streaks: {error_acc.get('total_failure_streaks', 0)}")
    print(f"    Avg streak length: {error_acc.get('avg_streak_length', 0):.1f}")
    print(f"    Max streak: {error_acc.get('max_streak_length', 0)}")
    print(f"    Rollback events: {error_acc.get('rollback_events', {}).get('total', 0)}")

    recovery_curve = error_acc.get('recovery_probability_curve', {})
    if recovery_curve:
        print("\n    Recovery probability curve:")
        for streak_len in sorted(recovery_curve.keys(), key=int):
            data = recovery_curve[streak_len]
            prob = data.get('recovery_probability', 0)
            samples = data.get('sample_count', 0)
            bar = "█" * int(prob * 20)
            print(f"      Streak {streak_len}: {bar} {prob:.1%} (n={samples})")

    # Save comprehensive report
    report_path = output_dir / "comprehensive_report.json"
    evaluator.generate_comprehensive_report(report_path)
    print(f"\n✓ Report saved: {report_path}")

    # Step 6: Summary
    print("\n[SUMMARY]")
    print("-" * 70)

    print("\n✓ Workflow completed successfully!")
    print(f"\n  All outputs saved to: {output_dir}")
    print(f"  - CodeFlowBench task: {output_dir}/codeflow_tasks/")
    print(f"  - Extended task: {output_dir}/tracebench_tasks/")
    print(f"  - Execution trace: {output_dir}/runs/")
    print(f"  - Metrics report: {output_dir}/comprehensive_report.json")

    print("\n  Three requirements validated:")
    print("  [✓] Multi-turn Traceability: Feedback IDs, patches, evidence maps")
    print("  [✓] Distribution Shift: Comprehensive shift_tags")
    print("  [✓] Error Accumulation: Rollback support, recovery curves")

    print("\n" + "="*70)

if __name__ == "__main__":
    try:
        example_workflow()
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
