# Phase 4 Performance Tuning Gate Definition

## Overview

Phase 4 Performance Tuning uses a **four-gate acceptance model** to judge whether an optimization candidate is safe to accept. All four gates must pass for a candidate to be marked `accepted`. If any gate fails, the candidate is `rejected` (or `diagnostic` if the failure is informative but not blocking for other candidates).

The four gates are evaluated after staged validation (short-smoke, optionally medium, optionally full) completes for a candidate.

## Four Gates

### 1. Performance Gate

**Purpose**: Verify that the optimization candidate actually improves the targeted performance metric.

| Field | Description |
|-------|-------------|
| `metric` | The performance metric being measured (e.g., `step_time`, `throughput_tokens_per_sec`, `gpu_busy_pct`) |
| `threshold` | The improvement threshold that constitutes a meaningful gain (e.g., `>= 5% improvement over baseline`, `step_time <= 0.85 * baseline_step_time`) |
| `result` | `passed` when the candidate meets the threshold; `failed` otherwise |

Performance gate uses Phase 3 baseline step time / throughput as the reference. The metric and threshold must be declared before validation begins; they cannot be retroactively adjusted to fit observed results.

### 2. Numerical Gate

**Purpose**: Verify that the optimization candidate does not introduce unacceptable loss or gradient drift relative to the Phase 3 baseline.

| Field | Description |
|-------|-------------|
| `comparison_mode` | How loss/grad is compared: `same_batch_loss_diff` (default), `windowed_loss_trend`, `grad_norm_ratio` |
| `tolerance` | The numerical tolerance for acceptance (e.g., `1e-3` for absolute loss diff, `0.5%` for relative loss diff) |
| `result` | `passed` when within tolerance; `failed` when drift exceeds tolerance |

Numerical gate uses `compare_loss_gate.py` from the `loongforge-performance-tuner` skill. The comparison mode and tolerance must be declared before validation begins. If the baseline does not have comparable loss checkpoints, the numerical gate cannot pass and the candidate is `rejected` or `diagnostic`.

### 3. Memory/Stability Gate

**Purpose**: Verify that the optimization candidate does not cause OOM, memory leaks, or numerical instability across validation steps.

| Field | Description |
|-------|-------------|
| `result` | `passed` when no OOM, no memory growth trend, and no NaN/Inf in loss or gradients; `failed` otherwise |

Memory/stability gate checks:
- No OOM errors during the validation run
- Memory usage is stable (no monotonically increasing trend across checkpoints)
- Loss and gradient norms contain no NaN or Inf values
- Peak memory usage does not exceed a safety margin (default: 90% of available GPU memory)

### 4. Scope Gate

**Purpose**: Verify that the optimization candidate stays within its declared scope and does not introduce unintended side effects.

| Field | Description |
|-------|-------------|
| `result` | `passed` when the candidate's changes are confined to the declared scope, no unintended files modified, no new dependencies introduced without approval; `failed` when scope is exceeded |

Scope gate checks:
- All file modifications are within the candidate's declared edit paths
- No new runtime dependencies introduced without explicit approval
- No changes to files outside the optimization scope (model code, conversion YAML, baseline scripts)
- If the candidate was run under an auto-loop envelope, all actions stay within the envelope

## Staged Validation Approach

Candidates are validated in stages of increasing cost and confidence:

| Stage | Duration | Purpose | Can Accept Candidate? |
|-------|----------|---------|----------------------|
| Short-smoke | 5-10 iterations | Quick triage: does the candidate run and show any improvement? | Only when the gate explicitly declares short-smoke is sufficient |
| Medium | 50-200 iterations | Confirm trend and gather more data points | When gate declares medium is sufficient |
| Full | Extended run (full training or long window) | Final confirmation with full statistical confidence | Always sufficient |

Escalation from one stage to the next requires:
1. The prior stage passes its gate checks
2. User approval (unless covered by an approved auto-loop envelope)

A candidate that fails at any stage does not escalate; it enters the `diagnosing` state.

## No-Candidate Pass

When profiling finds no actionable bottleneck (e.g., the workload is already well-optimized, or the bottleneck class is `host_sync_bound` with no optimization available in the current scope), Phase 4 may still pass if:
- The scope gate confirms that no optimization is needed
- All other gates are vacuously true (performance gate: no change requested; numerical gate: baseline unchanged; memory/stability gate: baseline unchanged)

In this case, `best_recipe` is `null` and `candidate_table` is empty.

## Reference Skills

- **`loongforge-nsys-profiler`**: Provides NSys trace capture, VeloQ quick scan, official stats analysis, sqlite-based bottleneck attribution, NVTX phase overlap analysis, and deep NSys performance reports. Used in Stage A (Profiling).
- **`loongforge-performance-tuner`**: Provides context discovery, candidate table management, staged validation orchestration, loss gate comparison, and optimization report maintenance. Used in Stage B (Optimization).
