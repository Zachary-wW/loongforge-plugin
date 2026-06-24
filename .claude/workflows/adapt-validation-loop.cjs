export const meta = {
  name: 'adapt-validation-loop',
  description: 'Run adapt skill Phase 0-3 with real GPU validators, then unified GT compare (memory + perf), dual-gate loop until both validators pass AND GT score meets threshold',
  phases: [
    { title: 'Init',           detail: 'Initialize run directory with loongforge-adapt CLI' },
    { title: 'Phase 0 Gen',   detail: 'Phase 0 architecture analysis — generate only, NO GT visibility' },
    { title: 'Phase 1 Gen',   detail: 'Phase 1 code generation — generate only, NO GT visibility' },
    { title: 'Phase 2 Gen',   detail: 'Phase 2 conversion code — generate only, NO GT visibility' },
    { title: 'Phase 3 Gen',   detail: 'Phase 3 loss-diff precision verification — generate only, NO GT visibility' },
    { title: 'GT Compare',    detail: 'Unified compare Phase 0-2 output vs GT (memory + perf + structural), record Phase 3 validator status' },
    { title: 'Dual-Gate',     detail: 'Check both validators AND GT score — exit only if both pass' },
    { title: 'Diagnose',      detail: 'Classify gaps as plugin deficiency vs context issue, with memory/perf root causes' },
    { title: 'Fix Plugin',    detail: 'Apply model-agnostic fixes to adapt plugin' },
    { title: 'Clear & Rerun', detail: 'Revert all GitHub PRs (Phase 0-3), clear local, loop back to Init' },
  ],
}

// PLUGIN_ROOT: absolute path to loongforge-plugin/ on this machine
// Set via args.plugin_root, or auto-detect from the workflow script's location.
const PLUGIN_ROOT = args.plugin_root || '/Users/weizhihao/workspace/agent_skills/loongforge-plugin'
const GROUND_TRUTH_BASE = args.ground_truth_base || '/Users/weizhihao/workspace/tmp_repo/0623'
const MAX_ITERATIONS = args.max_iterations || 3
const PASS_THRESHOLD = args.pass_threshold || 0.75
const RUN_DIR = args.run_dir || '/tmp/loongforge_adapt/ds_v4_loop_01'
const PHASES = args.phases || [0, 1, 2, 3]

// ── Preflight: verify paths exist ──────────────────────────────────────────
log(`PLUGIN_ROOT: ${PLUGIN_ROOT}`)
log(`GROUND_TRUTH_BASE: ${GROUND_TRUTH_BASE}`)
log(`RUN_DIR: ${RUN_DIR}`)
log(`PHASES: [${PHASES}]`)
log(`MAX_ITERATIONS: ${MAX_ITERATIONS}, PASS_THRESHOLD: ${PASS_THRESHOLD}`)

// ── Schemas ──────────────────────────────────────────────────────────────────

const COMPARISON_SCHEMA_V2 = {
  type: 'object',
  properties: {
    overall_score:         { type: 'number', description: '0.0 to 1.0 overall match (Phase 0-2 only)' },
    structural_score:     { type: 'number', description: '0.0 to 1.0 structural/code correctness' },
    memory_efficiency_score: { type: 'number', description: '0.0 to 1.0 — does generated code achieve GT-level memory efficiency (activation recomputation, memory partitioning, sequence parallelism)?' },
    performance_score:   { type: 'number', description: '0.0 to 1.0 — does generated code achieve GT-level runtime performance (kernel fusion, communication overlap, compute/comm ratio)?' },
    phase0_score:        { type: 'number' },
    phase1_score:        { type: 'number' },
    phase2_score:        { type: 'number' },
    phase3_validator_passed: { type: 'boolean', description: 'true if Phase 3 loss-diff validator passed (no GT structural compare for Phase 3)' },
    gaps: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id:                 { type: 'string' },
          phase:             { type: 'integer', description: 'Which phase this gap belongs to (0, 1, or 2)' },
          category:           { type: 'string', enum: ['missing_artifact', 'structural_mismatch', 'field_mismatch', 'logic_error', 'naming_mismatch', 'config_mismatch', 'memory_inefficiency', 'performance_regression'] },
          severity:          { type: 'string', enum: ['critical', 'major', 'minor'] },
          description:        { type: 'string' },
          generated_snippet:  { type: 'string' },
          ground_truth_snippet: { type: 'string' },
          plugin_root_cause:  { type: 'string', description: 'Which part of the plugin caused this gap' },
          fix_type:           { type: 'string', enum: ['plugin_fix', 'context_gap', 'acceptable_divergence'] },
        },
        required: ['id', 'phase', 'category', 'severity', 'description', 'plugin_root_cause', 'fix_type'],
      },
    },
  },
  required: ['overall_score', 'structural_score', 'memory_efficiency_score', 'performance_score', 'phase0_score', 'phase1_score', 'phase2_score', 'phase3_validator_passed', 'gaps'],
}

const DIAGNOSIS_SCHEMA = {
  type: 'object',
  properties: {
    plugin_fixes: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          gap_ids:           { type: 'array', items: { type: 'string' } },
          target_file:       { type: 'string', description: 'File in skills/adapt/ to modify' },
          fix_description:   { type: 'string' },
          is_model_agnostic: { type: 'boolean' },
          rationale:         { type: 'string' },
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
    success:       { type: 'boolean' },
  },
  required: ['cleared_files', 'success'],
}

// ── Ground truth file lists (ONLY used by COMPARE agents, NEVER by GENERATE agents) ──

const PHASE1_GT_FILES = [
  `${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/deepseek_v4_config.py`,
  `${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/deepseek_v4_attention.py`,
  `${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/deepseek_v4_csa.py`,
  `${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/deepseek_v4_rope.py`,
  `${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/deepseek_v4_model.py`,
  `${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/deepseek_v4_layer_spec.py`,
  `${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/loongforge/models/foundation/deepseek_v4/__init__.py`,
  `${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/configs/models/deepseek4/deepseek_v4_flash_base.yaml`,
  `${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/configs/models/deepseek4/ckpt_convert/deepseek_v4_convert.yaml`,
]

const PHASE2_GT_FILES = [
  `${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/examples/deepseek_v4/checkpoint_convert/convert_deepseek_v4_hf_to_mcore_fp8.sh`,
  `${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/examples/deepseek_v4/checkpoint_convert/convert_deepseek_v4_mcore_to_hf.sh`,
  `${GROUND_TRUTH_BASE}/ground_truth/baidu/hac-aiacc/AIAK-Training-Omni/configs/models/deepseek4/ckpt_convert/deepseek_v4_convert.yaml`,
]

const PHASE0_GT_REF_FILES = [
  `${GROUND_TRUTH_BASE}/hf_source/transformers/src/transformers/models/deepseek_v4/modeling_deepseek_v4.py`,
  `${GROUND_TRUTH_BASE}/hf_source/transformers/src/transformers/models/deepseek_v4/configuration_deepseek_v4.py`,
  `${GROUND_TRUTH_BASE}/hf_source/ckpt_meta/config.json`,
]

// ── Helper: generate agent prompt ────────────────────────────────────────────

function generateAgentPrompt(phaseNum) {
  const phaseDirs = { 0: 'phase0', 1: 'phase1', 2: 'phase2', 3: 'phase3' }
  const phaseDir = phaseDirs[phaseNum]

  const prerequisites = phaseNum === 0 ? ''
    : `3. Read ${[...Array(phaseNum).keys()].map(i => `Phase ${i} output at ${runDir}/phases/phase${i}_output.yml`).join(' — confirm status=passed.\n   ')} before proceeding.`

  const validatorCmd = `${PLUGIN_ROOT}/bin/loongforge-phase-loop --run-dir ${runDir} --phase ${phaseNum}`

  const outputSchema = phaseNum < 4
    ? `6. Write ${runDir}/phases/phase${phaseNum}_output.yml following the real schema at:
   ${PLUGIN_ROOT}/skills/adapt/references/phases/${phaseDir}/phase${phaseNum}_output_schema.yaml`
    : `6. Write ${runDir}/phases/phase3_output.yml following the real schema.`

  return `You are the Phase ${phaseNum} GENERATE agent. Your ONLY job is to produce Phase ${phaseNum} output
by following the real phase manual. You must NOT read, reference, or even know about
any ground truth files. You have NO access to ground truth.

CRITICAL: Do NOT search for, read, or reference any files under paths containing
"ground_truth" or "0623/ground_truth". If you encounter such paths, skip them.
Your job is pure generation from the HF source, model spec, and phase manuals.

1. Read and follow the real Phase ${phaseNum} manual at:
   ${PLUGIN_ROOT}/skills/adapt/references/phases/${phaseDir}/agent.md

2. Run directory: ${runDir}

${prerequisites}

4. If repos: block IS present (loop-engineering mode), follow the "Loop Engineering Hooks"
   section in the manual EXACTLY. YOU must:
   a) Pre-Edit: Create branch via gh CLI on the target repo
   b) Write your Phase ${phaseNum} code/artifacts
   c) Post-Edit: Open PR, merge it via gh CLI
   Translate gh_helper calls from the manual to direct gh CLI commands.

5. After writing code and merging your PR, run the validator loop (REAL execution, GPU available):
     ${validatorCmd}

   If exit code 0: Phase ${phaseNum} passed.
   If exit code 10 (FIX_NEEDED): read diagnosis from ${runDir}/phases/${phaseDir}/loop_state.yml,
     apply the fix, then re-run with --continue-fix.
   If exit code 1 (exhausted/human_needed): read escalation.md if it exists.

${outputSchema}

DO NOT read any ground truth files. Generate from the HF source, model_spec, and phase manuals ONLY.`
}

// ── Main loop ───────────────────────────────────────────────────────────────

let iteration = 0
let score = 0
let bestScore = 0
let memoryScore = 0
let perfScore = 0
let allGaps = []
let runDir = RUN_DIR
let phaseStatus = { 0: 'unknown', 1: 'unknown', 2: 'unknown', 3: 'unknown' }

log(`Using run directory: ${runDir}`)
log(`GT compare purpose: achieve GT-level memory efficiency and runtime performance`)

while (iteration < MAX_ITERATIONS) {
  iteration++
  log(`=== Iteration ${iteration}/${MAX_ITERATIONS} | score: ${score.toFixed(2)} | memory: ${memoryScore.toFixed(2)} | perf: ${perfScore.toFixed(2)} | threshold: ${PASS_THRESHOLD} ===`)

  // ══ PHASE: INIT RUN ════════════════════════════════════════════════════════
  phase('Init')

  if (iteration === 1) {
    await agent(
      `Initialize a new adapt skill run for the DS V4 model with loop engineering enabled.

Run this command via Bash:
  ${PLUGIN_ROOT}/bin/loongforge-adapt \\
    ${GROUND_TRUTH_BASE}/hf_source/ckpt_meta \\
    --model-name DeepSeek-V4-Flash-Base \\
    --run-dir ${runDir} \\
    --hf-impl-url https://github.com/huggingface/transformers \\
    --hf-impl-ref main \\
    --hf-impl-subpath src/transformers/models/deepseek_v4 \\
    --hf-ckpt-url https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-Base \\
    --loongforge-repo https://github.com/Zachary-wW/LoongForge \\
    --loongforge-base-ref main \\
    --megatron-repo https://github.com/Zachary-wW/Loong-Megatron \\
    --megatron-base-ref loong-main/core_v0.15.0

After running, verify the run directory was created at ${runDir}.
Report whether initialization succeeded.`,
      { label: 'init-run', phase: 'Init' }
    )
  } else {
    await agent(
      `Resume the adapt skill run from Phase 0 for a clean rerun.

Run via Bash:
  ${PLUGIN_ROOT}/bin/loongforge-adapt --resume ${runDir} --from-phase 0

This clears phase0-5 outputs and resets state.
Report success or failure.`,
      { label: 'resume-run', phase: 'Init' }
    )
  }

  // ══════════════════════════════════════════════════════════════════════════
  //  GENERATE AGENTS — these NEVER see ground truth paths
  // ══════════════════════════════════════════════════════════════════════════

  if (PHASES.includes(0)) {
    phase('Phase 0 Gen')
    await agent(generateAgentPrompt(0), { label: 'phase0-generate', phase: 'Phase 0 Gen' })
  }

  if (PHASES.includes(1)) {
    phase('Phase 1 Gen')
    await agent(generateAgentPrompt(1), { label: 'phase1-generate', phase: 'Phase 1 Gen' })
  }

  if (PHASES.includes(2)) {
    phase('Phase 2 Gen')
    await agent(generateAgentPrompt(2), { label: 'phase2-generate', phase: 'Phase 2 Gen' })
  }

  if (PHASES.includes(3)) {
    phase('Phase 3 Gen')
    await agent(generateAgentPrompt(3), { label: 'phase3-generate', phase: 'Phase 3 Gen' })
  }

  // ══════════════════════════════════════════════════════════════════════════
  //  READ PHASE STATUS — check validator outcomes from all phases
  // ══════════════════════════════════════════════════════════════════════════

  for (const p of PHASES) {
    const statusResult = await agent(
      `Read the Phase ${p} output YAML and extract the validator status.

Read ${runDir}/phases/phase${p}_output.yml

Extract the value of the "status" field (should be "passed" or "failed").
Return ONLY the status string. Example: "passed" or "failed"`,
      { label: `read-status-p${p}`, phase: 'GT Compare' }
    )
    phaseStatus[p] = (statusResult && statusResult.includes('passed')) ? 'passed' : 'failed'
  }

  log(`Validator status: Phase 0=${phaseStatus[0]}, Phase 1=${phaseStatus[1]}, Phase 2=${phaseStatus[2]}, Phase 3=${phaseStatus[3]}`)

  // ══════════════════════════════════════════════════════════════════════════
  //  UNIFIED GT COMPARE — reads ALL generated output + ALL ground truth
  //  ONLY for Phase 0-2 (structural). Phase 3: validator status only.
  // ══════════════════════════════════════════════════════════════════════════

  phase('GT Compare')

  const comparison = await agent(
    `You are the UNIFIED GT COMPARE agent. Your ONLY job is to READ all Phase 0-2 generated
output, compare it against ground truth, and score across THREE dimensions:
  1. STRUCTURAL CORRECTNESS — code structure, logic, naming matches GT
  2. MEMORY EFFICIENCY — does the generated code achieve GT-level memory optimization?
     Key patterns to check in GT:
     - Activation recomputation / selective checkpointing strategy
     - Memory partitioning (sequence parallelism, tensor model parallelism, pipeline parallelism config)
     - KV cache management (compressed KV for MLA, shared expert memory layout)
     - Gradient/optimizer memory layout (sharding, offloading)
     - Any memory_layout / memory_optimization / sequence_parallel flags in config
  3. RUNTIME PERFORMANCE — does the generated code achieve GT-level compute performance?
     Key patterns to check in GT:
     - Kernel fusion patterns (fused QKV, fused RMSNorm, fused SwiGLU)
     - Communication-computation overlap (overlap_grad_reduce, overlap_param_gather)
     - Micro-batch / global-batch sizing strategy
     - Expert parallelism / expert overlap scheduling
     - Any overlap_* / pipeline_* / barrier_pattern flags in config

You must NOT write any code, modify any files, or re-run any generation steps.
You are strictly read-only.

=== PHASE 0 ===
GENERATED: ${runDir}/phases/phase0/model_spec.yaml + ${runDir}/phases/phase0_output.yml
HF REFERENCE (not GT, but source truth):
${PHASE0_GT_REF_FILES.map(f => `- ${f}`).join('\n')}

=== PHASE 1 ===
Determine generated files from ${runDir}/phases/phase1_output.yml (artifacts.generated_files).
If loop-engineering mode, read merge_commit_sha from ${runDir}/phases/phase1/loop_state.yml
and access generated files from the repo at that commit.

GROUND TRUTH:
${PHASE1_GT_FILES.map(f => `- ${f}`).join('\n')}

=== PHASE 2 ===
Determine generated files from ${runDir}/phases/phase2_output.yml (artifacts.generated_files).
If loop-engineering mode, read merge_commit_sha from ${runDir}/phases/phase2/loop_state.yml.

GROUND TRUTH:
${PHASE2_GT_FILES.map(f => `- ${f}`).join('\n')}

=== PHASE 3 ===
Phase 3 does NOT have structural ground truth (it produces numerical outputs).
Only record whether the Phase 3 loss-diff validator passed.

=== SCORING ===
For each dimension (structural, memory, performance), score 0-1.0:
- overall_score = (structural + memory + performance) / 3
- Be STRICT on memory and performance: if the generated code is missing a memory
  optimization or performance pattern that exists in GT, that is a gap with
  category=memory_inefficiency or performance_regression.

List ALL gaps with:
- id: unique
- phase: 0, 1, or 2
- category: missing_artifact | structural_mismatch | field_mismatch | logic_error | naming_mismatch | config_mismatch | memory_inefficiency | performance_regression
- severity: critical | major | minor
- description: what is missing or wrong (be specific about memory/perf impact)
- generated_snippet: relevant generated code snippet
- ground_truth_snippet: corresponding GT snippet
- plugin_root_cause: which plugin component caused this gap
- fix_type: plugin_fix | context_gap | acceptable_divergence

Be HONEST and STRICT. Missing memory/perf optimizations are critical gaps —
the entire purpose of GT comparison is to achieve GT-level memory and performance.`,
    { label: 'unified-gt-compare', phase: 'GT Compare', schema: COMPARISON_SCHEMA_V2 }
  )

  // ══ PHASE: DUAL-GATE ════════════════════════════════════════════════════════
  phase('Dual-Gate')

  const comp = comparison || {
    overall_score: 0, structural_score: 0,
    memory_efficiency_score: 0, performance_score: 0,
    phase0_score: 0, phase1_score: 0, phase2_score: 0,
    phase3_validator_passed: false, gaps: [],
  }

  score = comp.overall_score || 0
  memoryScore = comp.memory_efficiency_score || 0
  perfScore = comp.performance_score || 0
  allGaps = comp.gaps || []
  bestScore = Math.max(bestScore, score)

  const allValidatorsPassed = PHASES.every(p => phaseStatus[p] === 'passed')
  const gtPassed = score >= PASS_THRESHOLD

  log(`Dual-Gate Check:`)
  log(`  Validators: ${allValidatorsPassed ? 'ALL PASSED' : 'SOME FAILED'} [${Object.entries(phaseStatus).map(([p,s]) => `P${p}=${s}`).join(', ')}]`)
  log(`  GT Score: ${score.toFixed(2)} (threshold: ${PASS_THRESHOLD}) → ${gtPassed ? 'PASS' : 'FAIL'}`)
  log(`  Structural: ${(comp.structural_score || 0).toFixed(2)} | Memory: ${memoryScore.toFixed(2)} | Perf: ${perfScore.toFixed(2)}`)
  log(`  Gaps: ${allGaps.length} (memory: ${allGaps.filter(g => g.category === 'memory_inefficiency').length}, perf: ${allGaps.filter(g => g.category === 'performance_regression').length}, structural: ${allGaps.filter(g => !['memory_inefficiency','performance_regression'].includes(g.category)).length})`)

  if (allValidatorsPassed && gtPassed) {
    log(`DUAL-GATE PASS: all validators passed AND GT score ${score.toFixed(2)} >= ${PASS_THRESHOLD}`)
    break
  }

  if (!allValidatorsPassed) {
    log(`DUAL-GATE BLOCKED: validators not all passed. Cannot proceed to GT improvement loop.`)
  }
  if (!gtPassed) {
    log(`DUAL-GATE BLOCKED: GT score ${score.toFixed(2)} < ${PASS_THRESHOLD}. Need to improve generated code quality.`)
  }

  // ══ PHASE: DIAGNOSE ════════════════════════════════════════════════════════
  phase('Diagnose')
  log(`Diagnosing ${allGaps.length} gaps for plugin fixes...`)

  const diagnosis = await agent(
    `You are diagnosing which gaps from the GT comparison can be fixed by improving the adapt plugin itself.

WHY GT COMPARISON EXISTS: The goal is to generate code that achieves GT-level
memory efficiency (显存) and runtime performance (性能). Memory and performance
gaps are the HIGHEST priority — structural gaps matter only if they cause
memory or performance regressions.

Current dual-gate status:
- Validators: ${Object.entries(phaseStatus).map(([p,s]) => `Phase ${p}=${s}`).join(', ')}
- GT score: ${score.toFixed(2)} (threshold: ${PASS_THRESHOLD})
- Structural: ${(comp.structural_score || 0).toFixed(2)} | Memory: ${memoryScore.toFixed(2)} | Perf: ${perfScore.toFixed(2)}

Gaps from comparison (JSON):
${JSON.stringify(allGaps, null, 2)}

Current adapt plugin structure to consider:
- ${PLUGIN_ROOT}/skills/adapt/references/phases/phase0/agent.md — Phase 0 HF parsing instructions
- ${PLUGIN_ROOT}/skills/adapt/references/phases/phase1/agent.md — Phase 1 code generation instructions
- ${PLUGIN_ROOT}/skills/adapt/references/phases/phase1/strategy_rules.yaml — Phase 1 structural rules
- ${PLUGIN_ROOT}/skills/adapt/references/phases/phase2/agent.md — Phase 2 conversion instructions
- ${PLUGIN_ROOT}/skills/adapt/references/phases/phase3/agent.md — Phase 3 loss-diff verification
- ${PLUGIN_ROOT}/skills/adapt/references/knowledge_base/ — Domain knowledge files
- ${PLUGIN_ROOT}/skills/adapt/loop_templates/phaseN/repair.md — Repair template
- ${PLUGIN_ROOT}/skills/adapt/SKILL.md — Overall skill instructions

For each gap, classify:
1. plugin_fix: A model-agnostic improvement to the plugin that would help with ANY model.
   PRIORITY: memory_inefficiency and performance_regression gaps are highest priority.
   The plugin must teach the generation agent about:
   - When and how to apply activation recomputation / selective checkpointing
   - Memory partitioning patterns (sequence parallelism, TP, PP config)
   - Communication-computation overlap patterns
   - Kernel fusion opportunities
   - Expert parallelism / scheduling strategies
2. context_gap: Needs more model-specific context — defer
3. acceptable_divergence: Different but valid approach — defer

ONLY propose fixes that are model-agnostic. Group related gaps into single fixes when they share a root cause.
For memory/perf gaps, the fix should add explicit instructions or rules to the phase manuals/KB
that guide the generation agent to produce memory-efficient and performant code.`,
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

If this fix addresses a memory_inefficiency or performance_regression gap:
- Add explicit guidance about WHEN and HOW to apply the optimization
- Reference the GT pattern as a "recommended practice" in the manual/KB
- Ensure the generation agent will naturally produce memory-efficient and performant code

After making the change, verify the file still reads coherently.`,
      { label: `fix-${idx}: ${fix.fix_description.slice(0, 40)}`, phase: 'Fix Plugin' }
    )
  )

  const appliedFixes = fixResults.filter(Boolean).length
  log(`Applied ${appliedFixes}/${diagnosis.plugin_fixes.length} plugin fixes`)

  // ══ PHASE: CLEAR & RERUN ══════════════════════════════════════════════════
  phase('Clear & Rerun')

  // Step 1: Revert merged PRs on GitHub repos from ALL phases (0-3)
  const prNumbers = []
  for (const phaseNum of PHASES) {
    const outputPath = `${runDir}/phases/phase${phaseNum}_output.yml`
    const prData = await agent(
      `Read the Phase ${phaseNum} output file to extract the merged PR number(s).

Read ${outputPath}

Extract ALL PR numbers from the file — there may be a base PR and a main PR.
Look for fields: pr.number, fix_pr_number, or any field containing a PR URL/number.
Also check ${runDir}/phases/phase${phaseNum}/loop_state.yml for pr_number and fix_pr_number.

Return ONLY the PR numbers as a JSON array of integers. If no PR was merged, return [].
Example: [13, 14] or [20]`,
      { label: `extract-prs-p${phaseNum}`, phase: 'Clear & Rerun' }
    )
    if (prData) {
      try {
        const nums = JSON.parse(prData)
        if (Array.isArray(nums)) prNumbers.push(...nums.filter(n => typeof n === 'number' && n > 0))
      } catch(e) {
        const matches = prData.match(/\b(\d{1,4})\b/g)
        if (matches) prNumbers.push(...matches.map(Number).filter(n => n > 0))
      }
    }
  }

  const allPrsToRevert = [...new Set([...prNumbers])].sort((a,b) => b-a)
  log(`PRs to revert on LoongForge: ${allPrsToRevert.length > 0 ? allPrsToRevert.join(', ') : '(none found)'}`)

  if (allPrsToRevert.length > 0) {
    for (const prNum of allPrsToRevert) {
      await agent(
        `Revert merged PR #${prNum} on Zachary-wW/LoongForge, then merge the revert PR.

Step A — Create the revert PR:
  gh pr revert ${prNum} --repo Zachary-wW/LoongForge \\
    --title "revert: PR #${prNum} (adapt-validation-loop pre-rerun)" \\
    --body "Reverting before re-running adapt-validation-loop with improved plugin. GT comparison showed memory/performance gaps; plugin has been updated with new optimization rules."

If that fails with merge conflict, open it as draft:
  gh pr revert ${prNum} --repo Zachary-wW/LoongForge --draft

Step B — After the revert PR is created, merge it:
  Read the revert PR number from the output of Step A, then:
  gh pr merge <revert_pr_number> --repo Zachary-wW/LoongForge --squash --delete-branch

Report success or failure for PR #${prNum}.`,
        { label: `revert-pr-${prNum}`, phase: 'Clear & Rerun' }
      )
    }
  }

  // Step 2: Clear local run directory
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

  log(`Cleared ${(clearResult && clearResult.cleared_files) ? clearResult.cleared_files.length : 0} files. GitHub PRs reverted: ${allPrsToRevert.length}. Looping back to Init.`)
}

// ── Final report ────────────────────────────────────────────────────────────
log(`=== Adapt Validation Loop Complete ===`)
log(`Iterations: ${iteration}/${MAX_ITERATIONS}`)
log(`Final score: ${score.toFixed(2)} (threshold: ${PASS_THRESHOLD})`)
log(`Best score: ${bestScore.toFixed(2)}`)
log(`Structural: ${(comparison && comparison.structural_score || 0).toFixed(2)} | Memory: ${memoryScore.toFixed(2)} | Perf: ${perfScore.toFixed(2)}`)
log(`Validator status: ${Object.entries(phaseStatus).map(([p,s]) => `P${p}=${s}`).join(', ')}`)
log(`Status: ${(PHASES.every(p => phaseStatus[p] === 'passed') && score >= PASS_THRESHOLD) ? 'PASSED' : 'DID NOT PASS — review gaps and consider manual plugin improvements'}`)
log(`Total gaps: ${allGaps.length} (memory: ${allGaps.filter(g => g.category === 'memory_inefficiency').length}, perf: ${allGaps.filter(g => g.category === 'performance_regression').length})`)

return {
  iterations: iteration,
  final_score: score,
  best_score: bestScore,
  structural_score: comparison && comparison.structural_score || 0,
  memory_efficiency_score: memoryScore,
  performance_score: perfScore,
  validators_passed: PHASES.every(p => phaseStatus[p] === 'passed'),
  passed: PHASES.every(p => phaseStatus[p] === 'passed') && score >= PASS_THRESHOLD,
  total_gaps: allGaps.length,
  memory_gaps: allGaps.filter(g => g.category === 'memory_inefficiency').length,
  perf_gaps: allGaps.filter(g => g.category === 'performance_regression').length,
}
