export const meta = {
  name: 'adapt-validation-loop',
  description: 'Run real adapt skill Phase 0-2 with loop engineering (gh PR/issue/merge), compare with ground truth, fix plugin, rerun',
  phases: [
    { title: 'Init',          detail: 'Initialize run directory with loongforge-adapt CLI' },
    { title: 'Phase 0',      detail: 'Execute Phase 0 via real agent.md + loongforge-phase-loop + loongforge-phase-gate' },
    { title: 'Phase 1',      detail: 'Execute Phase 1 via real agent.md + loongforge-phase-loop + Compare gate' },
    { title: 'Phase 2',      detail: 'Execute Phase 2 via real agent.md + loongforge-phase-loop + Compare gate' },
    { title: 'Overall Score',detail: 'Aggregate comparison scores across all phases' },
    { title: 'Diagnose',     detail: 'Classify gaps as plugin deficiency vs context issue' },
    { title: 'Fix Plugin',   detail: 'Apply model-agnostic fixes to adapt plugin' },
    { title: 'Clear & Rerun',detail: 'Resume from phase 0, re-compare' },
  ],
}

const PLUGIN_ROOT = '/Users/weizhihao/workspace/agent_skills/loongforge-plugin'
const GROUND_TRUTH_BASE = args.ground_truth_base || '/Users/weizhihao/workspace/tmp_repo/0623'
const MAX_ITERATIONS = args.max_iterations || 3
const PASS_THRESHOLD = args.pass_threshold || 0.75

// ── Schemas ──────────────────────────────────────────────────────────────────

const COMPARISON_SCHEMA = {
  type: 'object',
  properties: {
    overall_score: { type: 'number', description: '0.0 to 1.0 overall match score' },
    phase0_score: { type: 'number' },
    phase1_score: { type: 'number' },
    phase2_score: { type: 'number' },
    gaps: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'string' },
          category: { type: 'string', enum: ['missing_artifact', 'structural_mismatch', 'field_mismatch', 'logic_error', 'naming_mismatch', 'config_mismatch'] },
          severity: { type: 'string', enum: ['critical', 'major', 'minor'] },
          description: { type: 'string' },
          generated_snippet: { type: 'string' },
          ground_truth_snippet: { type: 'string' },
          plugin_root_cause: { type: 'string', description: 'Which part of the plugin caused this gap' },
          fix_type: { type: 'string', enum: ['plugin_fix', 'context_gap', 'acceptable_divergence'] },
        },
        required: ['id', 'category', 'severity', 'description', 'plugin_root_cause', 'fix_type'],
      },
    },
  },
  required: ['overall_score', 'phase0_score', 'phase1_score', 'phase2_score', 'gaps'],
}

const DIAGNOSIS_SCHEMA = {
  type: 'object',
  properties: {
    plugin_fixes: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          gap_ids: { type: 'array', items: { type: 'string' } },
          target_file: { type: 'string', description: 'File in skills/adapt/ to modify' },
          fix_description: { type: 'string' },
          is_model_agnostic: { type: 'boolean' },
          rationale: { type: 'string' },
        },
        required: ['gap_ids', 'target_file', 'fix_description', 'is_model_agnostic', 'rationale'],
      },
    },
    deferred: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          gap_id: { type: 'string' },
          reason: { type: 'string' },
        },
        required: ['gap_id', 'reason'],
      },
    },
  },
  required: ['plugin_fixes', 'deferred'],
}

const CLEAR_SCHEMA = {
  type: 'object',
  properties: {
    cleared_files: { type: 'array', items: { type: 'string' } },
    success: { type: 'boolean' },
  },
  required: ['cleared_files', 'success'],
}

// ── Fix cycle helper prompt fragment ────────────────────────────────────────

const FIX_CYCLE_INSTRUCTIONS = `
If loongforge-phase-loop exits with code 10 (FIX_NEEDED):
  1. Read the diagnosis from the loop state: <run_dir>/phases/phase<N>/loop_state.yml
     Look at last_validator_summary for the validator name, status, and failure_signature.
  2. Read the repair template at: ${PLUGIN_ROOT}/skills/adapt/loop_templates/phase<N>/repair.md
     If the template does not exist, read the diagnose classifier output from attempts.jsonl.
  3. Write the fix code on the branch that the loop controller created.
     The branch name is in loop_state.yml under the attempt counter.
     Push your fix to that branch.
  4. Re-run the loop: loongforge-phase-loop --run-dir <run_dir> --phase <N> --continue-fix
  5. Repeat steps 1-4 until the loop exits 0 (passed) or 1 (exhausted/human_needed).
  6. If the loop exits 1, read escalation.md if it exists and report the failure.`

// ── Main loop ───────────────────────────────────────────────────────────────

let iteration = 0
let score = 0
let bestScore = 0
let allGaps = []
let runDir = ''

while (iteration < MAX_ITERATIONS && score < PASS_THRESHOLD) {
  iteration++
  log(`=== Iteration ${iteration}/${MAX_ITERATIONS} | current score: ${score.toFixed(2)} | threshold: ${PASS_THRESHOLD} ===`)

  // ══ PHASE: INIT RUN ════════════════════════════════════════════════════════
  phase('Init')

  if (iteration === 1) {
    const initResult = await agent(
      `Initialize a new adapt skill run for the DS V4 model with loop engineering enabled.

Run this command via Bash:
  ${PLUGIN_ROOT}/bin/loongforge-adapt \\
    ${GROUND_TRUTH_BASE}/hf_source/ckpt_meta \\
    --model-name DeepSeek-V4-Flash-Base \\
    --hf-impl-url https://github.com/huggingface/transformers \\
    --hf-impl-ref main \\
    --hf-impl-subpath src/transformers/models/deepseek_v4 \\
    --hf-ckpt-url https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Base \\
    --loongforge-repo https://github.com/Zachary-wW/LoongForge \\
    --loongforge-base-ref main \\
    --megatron-repo https://github.com/Zachary-wW/Loong-Megatron \\
    --megatron-base-ref loong-main/core_v0.15.0

If that fails, try with --dry-run for a test run.

After running, read the run directory path from the output.
The run_dir is typically under /tmp/loongforge_adapt/ or the path specified by --run-dir.
Report the run_dir path.`,
      { label: 'init-run', phase: 'Init' }
    )
    // Extract run_dir from agent output — use args.run_dir (required for first iteration)
    runDir = args.run_dir || ''
    if (!runDir) {
      log('ERROR: args.run_dir must be provided for the first iteration. Pass it via Workflow args.')
      break
    }
    log(`Run directory: ${runDir}`)
  } else {
    const resumeResult = await agent(
      `Resume the adapt skill run from Phase 0 for a clean rerun.

Run via Bash:
  ${PLUGIN_ROOT}/bin/loongforge-adapt --resume ${runDir} --from-phase 0

This clears phase0-5 outputs and resets state.
Report success or failure.`,
      { label: 'resume-run', phase: 'Init' }
    )
  }

  // ══ PHASE: PHASE 0 ════════════════════════════════════════════════════════
  phase('Phase 0')

  await agent(
    `Execute Phase 0 of the adapt skill following the REAL phase manual.

1. Read and follow the real Phase 0 manual at:
   ${PLUGIN_ROOT}/skills/adapt/references/phases/phase0/agent.md

2. Run directory: ${runDir}

3. Read run_inputs.yml at ${runDir}/run_inputs.yml to check if repos: block is present.

4. If repos: block IS present (loop-engineering mode), follow the "Loop Engineering Hooks"
   section in the Phase 0 manual. Use the loongforge-phase-loop CLI for the FSM closed loop:
     ${PLUGIN_ROOT}/bin/loongforge-phase-loop --run-dir ${runDir} --phase 0 [--dry-run]

5. ${FIX_CYCLE_INSTRUCTIONS.replace(/<run_dir>/g, runDir).replace(/<N>/g, '0')}

6. After the phase loop completes (exit 0), validate with the structural gate:
     ${PLUGIN_ROOT}/bin/loongforge-phase-gate --run-dir ${runDir} --phase 0

7. Write ${runDir}/phases/phase0_output.yml following the real schema at:
   ${PLUGIN_ROOT}/skills/adapt/references/phases/phase0/phase0_output_schema.yaml

The adapt skill's real infrastructure handles gh interaction (PR/issue/merge).
Trust the agent.md manual and the CLI tools — do NOT reimplement their logic.`,
    { label: 'phase0-execute', phase: 'Phase 0' }
  )

  // ══ PHASE: PHASE 1 ════════════════════════════════════════════════════════
  phase('Phase 1')

  const phase1Comparison = await agent(
    `Execute Phase 1 of the adapt skill following the REAL phase manual.

1. Read and follow the real Phase 1 manual at:
   ${PLUGIN_ROOT}/skills/adapt/references/phases/phase1/agent.md

2. Run directory: ${runDir}

3. Read Phase 0 output at ${runDir}/phases/phase0_output.yml — confirm status=passed before proceeding.

4. Read run_inputs.yml — if repos: block present, follow the "Loop Engineering Hooks"
   section. Use the loongforge-phase-loop CLI for the FSM closed loop (PR/merge):
     ${PLUGIN_ROOT}/bin/loongforge-phase-loop --run-dir ${runDir} --phase 1 [--dry-run]

5. ${FIX_CYCLE_INSTRUCTIONS.replace(/<run_dir>/g, runDir).replace(/<N>/g, '1')}

6. VALIDATION GATE: Since the real Phase 1 validator (loss alignment) requires GPU
   and we are running on a local Mac, use Compare against ground truth instead:
   After the loop merges your code (or after you write the code in local mode),
   compare the generated files against ground truth:

   GENERATED files (read from the LoongForge repo at the merge commit, or from local paths):
   - ${runDir}/phases/phase1/ (local artifacts if any)
   - If loop engineering: read merge_commit_sha from ${runDir}/phases/phase1/loop_state.yml,
     then checkout that commit in the LoongForge repo to compare.

   GROUND TRUTH files:
   - ${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/deepseek_v4_config.py
   - ${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/deepseek_v4_attention.py
   - ${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/deepseek_v4_csa.py
   - ${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/deepseek_v4_rope.py
   - ${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/deepseek_v4_model.py
   - ${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/deepseek_v4_layer_spec.py
   - ${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/__init__.py
   - ${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/configs/models/deepseek4/deepseek_v4_flash_base.yaml
   - ${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/configs/models/deepseek4/ckpt_convert/deepseek_v4_convert.yaml

   Score each pair 0-1.0. List gaps with plugin_root_cause and fix_type.
   This comparison IS the validation gate for Phase 1 (substituting for the GPU validator).

7. Write ${runDir}/phases/phase1_output.yml following the real schema at:
   ${PLUGIN_ROOT}/skills/adapt/references/phases/phase1/phase1_output_schema.yaml`,
    { label: 'phase1-execute', phase: 'Phase 1', schema: COMPARISON_SCHEMA }
  )

  // ══ PHASE: PHASE 2 ════════════════════════════════════════════════════════
  phase('Phase 2')

  const phase2Comparison = await agent(
    `Execute Phase 2 of the adapt skill following the REAL phase manual.

1. Read and follow the real Phase 2 manual at:
   ${PLUGIN_ROOT}/skills/adapt/references/phases/phase2/agent.md

2. Run directory: ${runDir}

3. Read Phase 0 output at ${runDir}/phases/phase0_output.yml — confirm status=passed.
   Read Phase 1 output at ${runDir}/phases/phase1_output.yml — confirm status=passed.

4. If repos: block present, follow the "Loop Engineering Hooks" section.
   Use: ${PLUGIN_ROOT}/bin/loongforge-phase-loop --run-dir ${runDir} --phase 2 [--dry-run]

5. ${FIX_CYCLE_INSTRUCTIONS.replace(/<run_dir>/g, runDir).replace(/<N>/g, '2')}

6. VALIDATION GATE: Same as Phase 1 — GPU validator not available on Mac.
   Compare the generated conversion code against ground truth:

   GENERATED files:
   - ${runDir}/phases/phase2/ (local artifacts)
   - If loop engineering: checkout merge commit from ${runDir}/phases/phase2/loop_state.yml

   GROUND TRUTH files:
   - ${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/examples/deepseek_v4/checkpoint_convert/convert_deepseek_v4_hf_to_mcore_fp8.sh
   - ${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/examples/deepseek_v4/checkpoint_convert/convert_deepseek_v4_mcore_to_hf.sh
   - ${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/configs/models/deepseek4/ckpt_convert/deepseek_v4_convert.yaml

   Score 0-1.0. List gaps.

7. Write ${runDir}/phases/phase2_output.yml following the real schema at:
   ${PLUGIN_ROOT}/skills/adapt/references/phases/phase2/phase2_output_schema.yaml`,
    { label: 'phase2-execute', phase: 'Phase 2', schema: COMPARISON_SCHEMA }
  )

  // ══ PHASE: OVERALL SCORE ═══════════════════════════════════════════════════
  phase('Overall Score')

  // The Phase 1 and Phase 2 agents already returned COMPARISON_SCHEMA results
  // with scores. We need to also evaluate Phase 0.
  const phase0Comparison = await agent(
    `Score the Phase 0 architecture analysis output against ground truth expectations.

Read the Phase 0 output:
- ${runDir}/phases/phase0/model_spec.yaml (or equivalent primary output)
- ${runDir}/phases/phase0_output.yml

Also read the HF source for reference:
- ${GROUND_TRUTH_BASE}/hf_source/transformers/src/transformers/models/deepseek_v4/modeling_deepseek_v4.py
- ${GROUND_TRUTH_BASE}/hf_source/transformers/src/transformers/models/deepseek_v4/configuration_deepseek_v4.py
- ${GROUND_TRUTH_BASE}/hf_source/ckpt_meta/config.json

Score Phase 0 completeness (0-1.0): does the output capture ALL novel architectural features
(MLA, MoE with hash routing, HyperConnection, CSA/HCA, Compressor, GroupedLinear, SwiGLU clamp,
MTP, Indexer, YaRN RoPE)? List gaps.`,
    { label: 'score-phase0', phase: 'Overall Score', schema: COMPARISON_SCHEMA }
  )

  // Aggregate scores from Phase 0, 1, 2 comparisons
  const p0 = phase0Comparison || { overall_score: 0, phase0_score: 0, phase1_score: 0, phase2_score: 0, gaps: [] }
  const p1 = phase1Comparison || { overall_score: 0, phase0_score: 0, phase1_score: 0, phase2_score: 0, gaps: [] }
  const p2 = phase2Comparison || { overall_score: 0, phase0_score: 0, phase1_score: 0, phase2_score: 0, gaps: [] }

  const phase0s = Math.max(p0.phase0_score || 0, p1.phase0_score || 0, p2.phase0_score || 0)
  const phase1s = Math.max(p0.phase1_score || 0, p1.phase1_score || 0, p2.phase1_score || 0)
  const phase2s = Math.max(p0.phase2_score || 0, p1.phase2_score || 0, p2.phase2_score || 0)
  score = (phase0s + phase1s + phase2s) / 3
  bestScore = Math.max(bestScore, score)
  allGaps = [...(p0.gaps || []), ...(p1.gaps || []), ...(p2.gaps || [])]

  log(`Iteration ${iteration} — score: ${score.toFixed(2)} (p0: ${phase0s.toFixed(2)}, p1: ${phase1s.toFixed(2)}, p2: ${phase2s.toFixed(2)}), gaps: ${allGaps.length}`)

  if (score >= PASS_THRESHOLD) {
    log(`PASS threshold reached! Score: ${score.toFixed(2)} >= ${PASS_THRESHOLD}`)
    break
  }

  // ══ PHASE: DIAGNOSE ════════════════════════════════════════════════════════
  phase('Diagnose')
  log(`Diagnosing ${allGaps.length} gaps for plugin fixes...`)

  const diagnosis = await agent(
    `You are diagnosing which gaps from the comparison can be fixed by improving the adapt plugin itself.

Gaps from comparison (JSON):
${JSON.stringify(allGaps, null, 2)}

Current adapt plugin structure to consider:
- ${PLUGIN_ROOT}/skills/adapt/references/phases/phase0/agent.md — Phase 0 HF parsing instructions
- ${PLUGIN_ROOT}/skills/adapt/references/phases/phase1/agent.md — Phase 1 code generation instructions
- ${PLUGIN_ROOT}/skills/adapt/references/phases/phase2/agent.md — Phase 2 conversion instructions
- ${PLUGIN_ROOT}/skills/adapt/references/knowledge_base/ — Domain knowledge files
- ${PLUGIN_ROOT}/skills/adapt/loop_templates/phaseN/repair.md — Repair template
- ${PLUGIN_ROOT}/skills/adapt/SKILL.md — Overall skill instructions

For each gap, classify:
1. plugin_fix: A model-agnostic improvement to the plugin that would help with ANY model
2. context_gap: Needs more DS V4 specific context that can't be generalized — defer
3. acceptable_divergence: Different but valid approach — defer

ONLY propose fixes that are model-agnostic. Group related gaps into single fixes when they share a root cause.`,
    { label: 'diagnose-gaps', phase: 'Diagnose', schema: DIAGNOSIS_SCHEMA }
  )

  if (!diagnosis || !diagnosis.plugin_fixes || diagnosis.plugin_fixes.length === 0) {
    log('No plugin fixes identified. Stopping loop.')
    break
  }

  log(`Diagnosed: ${diagnosis.plugin_fixes.length} plugin fixes, ${diagnosis.deferred.length} deferred`)

  // ══ PHASE: FIX PLUGIN ══════════════════════════════════════════════════════
  phase('Fix Plugin')

  const fixResults = await pipeline(
    diagnosis.plugin_fixes.filter(f => f.is_model_agnostic),
    (fix, idx) => agent(
      `Apply this model-agnostic fix to the adapt plugin.

FIX: ${fix.fix_description}

TARGET FILE: ${fix.target_file}

AFFECTED GAPS: ${fix.gap_ids.join(', ')}

RATIONALE: ${fix.rationale}

Read the target file first, then make the minimal, precise change needed.
The fix must be model-agnostic — it improves the plugin for ANY model adaptation, not just DS V4.
Do NOT hardcode DS V4 specifics. Instead, add general instructions, checklists, patterns, or knowledge.

After making the change, verify the file still reads coherently.`,
      { label: `fix-${idx}: ${fix.fix_description.slice(0, 40)}`, phase: 'Fix Plugin' }
    )
  )

  const appliedFixes = fixResults.filter(Boolean).length
  log(`Applied ${appliedFixes}/${diagnosis.plugin_fixes.length} plugin fixes`)

  // ══ PHASE: CLEAR & RERUN ══════════════════════════════════════════════════
  phase('Clear & Rerun')

  const clearResult = await agent(
    `Clear phase outputs and prepare for a clean rerun.

Run via Bash:
  ${PLUGIN_ROOT}/bin/loongforge-adapt --resume ${runDir} --from-phase 0

This clears phase0-5 outputs and resets state.
Also remove any cloned comparison repos:
  rm -rf /tmp/loongforge-compare 2>/dev/null || true

Report what was cleared.`,
    { label: 'clear-rerun', phase: 'Clear & Rerun', schema: CLEAR_SCHEMA }
  )

  log(`Cleared ${(clearResult && clearResult.cleared_files) ? clearResult.cleared_files.length : 0} files. Looping back to Init.`)
}

// ── Final report ────────────────────────────────────────────────────────────
log(`=== Adapt Validation Loop Complete ===`)
log(`Iterations: ${iteration}/${MAX_ITERATIONS}`)
log(`Final score: ${score.toFixed(2)} (threshold: ${PASS_THRESHOLD})`)
log(`Best score: ${bestScore.toFixed(2)}`)
log(`Status: ${score >= PASS_THRESHOLD ? 'PASSED' : 'DID NOT PASS — review gaps and consider manual plugin improvements'}`)
log(`Total gaps identified: ${allGaps.length}`)

return {
  iterations: iteration,
  final_score: score,
  best_score: bestScore,
  passed: score >= PASS_THRESHOLD,
  total_gaps: allGaps.length,
}
