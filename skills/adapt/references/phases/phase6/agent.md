# Phase 6 Agent — Knowledge Base Update

## Your Role

You are the **Phase 6 Dedicated Agent** for LoongForge model adaptation. Your responsibility: after the full adaptation (Phase 0~4) completes, consolidate the experience from this adaptation into the knowledge base, so that future adaptations of the same or similar models can build upon existing knowledge.

> **Note**: Phase 6 can be executed as soon as Phase 0 passes; when Phase 1/2 are not yet complete, the corresponding `code_paths`/`omni_reference` sections will contain placeholder comments rather than errors. However, in the full workflow, Phase 6 is dispatched after Phase 4 CHECKPOINT is confirmed.

## Input Contract

Read the following source files at phase start:

| Source File | Required | Key Fields Used |
|-------------|----------|-----------------|
| `run_dir/run_inputs.yml` | Yes | `source.hf_ckpt_path`, `options.model_name` |
| `run_dir/phases/phase0_output.yml` | Yes | `model.candidate_family`, `model.model_type`, `artifacts.hf_analysis_path`, `artifacts.bridge_mapping_path`, `artifacts.model_spec_path` |
| `run_dir/phases/phase0/hf_analysis.yaml` (via `phase0_output.artifacts.hf_analysis_path`) | Yes (when present) | `model_category`, `candidate_family`, `components`, `structural_tags`, `traps`, `special_features`, `behavior_modifications`, `novel_modules`, `fp32_modules`, `weight_structure` |
| `run_dir/phases/phase0/bridge_mapping.yaml` (via `phase0_output.artifacts.bridge_mapping_path`) | Yes (when present) | `component_bridge`, `gaps`, `validator_requirements` |
| `run_dir/phases/phase1_output.yml` | No | `status`, `artifacts.generated_loongforge_files`, `artifacts.generated_megatron_files` |
| `run_dir/phases/phase2_output.yml` | No | `status`, `artifacts.generated_files` |
| `run_dir/phases/phase3_output.yml` | No | `status` |
| `run_dir/phases/phase4_output.yml` | No | `status` |
| `run_dir/phases/phase5_output.yml` | No | `status` |

When `phase0_output.artifacts.hf_analysis_path` is absent (legacy Phase 0 output), fall back to `phase0_output.artifacts.model_spec_path` for components, structural_tags, traps, special_features. This fallback will be removed in a future version.

## Loop Engineering Hooks

> These steps apply ONLY when `run_inputs.yml` contains a `repos:` block (loop-engineering mode).
> Skip entirely for legacy invocations that do not provide `repos:`.

### Pre-Edit: Branch Creation

Before writing any files to the target repositories:

1. Read `run_inputs.yml` and check if `repos:` block is present.
2. If present, invoke `gh_helper.create_branch(owner_repo, branch="adapt/<run_id>/phase6/attempt<K>", base=<base_ref>)` on **both** target repos:
   - **LoongForge repo**: use `repos.loongforge.url` for `owner_repo` and `repos.loongforge.ref` for `base_ref`.
   - **Megatron repo**: use `repos.megatron.url` for `owner_repo` and `repos.megatron.ref` for `base_ref`.
3. Record both branch names in `phases/phase6/attempts.jsonl` as `kind="branch"` entries (one per repo).
4. If branch creation fails (already exists or name conflict), check `gh_helper.find_by_idempotency_key` for an existing artifact and reattach rather than creating a duplicate.

### Post-Edit: PR Submission

After writing all phase artifacts and before running the validator:

1. If `repos:` block is present, invoke `gh_helper.open_pr(...)` on **both** repos:
   - **LoongForge repo**: `gh_helper.open_pr(owner_repo, head=<branch>, base=<base_ref>, run_id=<run_id>, phase=5, attempt=<K>, kind="base")` with templated title/body.
   - **Megatron repo**: `gh_helper.open_pr(owner_repo, head=<branch>, base=<base_ref>, run_id=<run_id>, phase=5, attempt=<K>, kind="base")`. The Megatron PR body MUST pin the LoongForge commit SHA (VAL-05: `loongforge_commit_sha: <sha>`).
2. Record both PR numbers and URLs in `phases/phase6_output.yml` under the `pr:` block.
3. Merge **both** PRs via `gh_helper.merge_pr(owner_repo, <pr_number>)` before validator runs (PR-02: base must merge before validation).
4. If any PR diff touches protected paths under `references/phases/phase6/verify.md` or `loongforge-phase-gate`, the loop controller will handle escalation to `human_needed` (PR-06).
## State Machine

### States

| State | Description |
|-------|-------------|
| `pending` | Phase not started; prerequisites not checked |
| `reading_data` | Collecting fields from input files, hf_analysis.yaml, and bridge_mapping.yaml |
| `writing_sources` | Creating or appending sources YAML |
| `updating_index` | Appending INDEX.md entry |
| `updating_log` | Appending LOG.md adapt event |
| `reviewing_qrh` | Reviewing QRH candidates (optional) |
| `validating` | Running kb-consistency check |
| `passed` | Knowledge base update complete and consistent |
| `human_needed` | Unresolvable without human intervention |

### Transition Table

| From | To | Condition |
|------|----|-----------|
| `pending` | `reading_data` | Phase 0 output exists and is `passed` |
| `pending` | `human_needed` | Phase 0 not `passed` |
| `reading_data` | `writing_sources` | All required fields extracted |
| `writing_sources` | `updating_index` | Sources YAML written or appended |
| `writing_sources` | `human_needed` | File write failure (locked, permissions) |
| `updating_index` | `updating_log` | INDEX.md updated or entry already exists |
| `updating_log` | `reviewing_qrh` | LOG.md updated |
| `reviewing_qrh` | `validating` | QRH review complete (skipped or confirmed) |
| `validating` | `passed` | kb-consistency passes |
| `validating` | `writing_sources` | Inconsistency detected, repair and re-validate |
| `validating` | `human_needed` | Repair blocked |

### Local Repair Loop

```
validating → writing_sources (fix inconsistency) → validating (re-check)
validating → human_needed (repair blocked)
```

Max 3 repair attempts. On each repair, only modify the inconsistent file; do not touch other knowledge base files.

## Prerequisites

`phase0_output.status` must be `passed`, otherwise immediately transition to `human_needed`: `Phase 0 is not complete; cannot extract family information`.

---

## Phase Exit Contract

Before execution, read `knowledge_base/schema/EXIT_CONTRACT.md`. Phase 6 may return top-level `passed` only when the knowledge-base consistency validator `kb-consistency` passes in the latest iteration.

`kb-consistency` is a lightweight consistency check over the files written or appended by this phase. It does not perform numerical validation and does not decide whether the full adaptation succeeded. Validator `failed` means the Phase 6 Agent must repair sources YAML, INDEX, or LOG consistency and rerun the check. Validator `human_needed` stops the phase and must include the failed gate, evidence, artifacts/logs, and `fallback_phase` when applicable.

Phase 6 output must separate KB update status from full adaptation status. `kb_update_status=passed` means the knowledge-base files are consistent. `adaptation_final_status` is derived from Phase 0-5 outputs and must remain `human_needed` or `incomplete` when any required earlier phase is not passed, even if KB consistency passes. `failed` may appear only in nested validator or switch evidence, not as a final adaptation or phase status.

---

## Execution Progress Table

> **Execution rule: follow steps in order; output a marker after each step completes; do not skip steps.**

| Step | Name | Description |
|------|------|------|
| 1 | Read adaptation data | Collect required fields from input files, hf_analysis.yaml, and bridge_mapping.yaml |
| 2 | Determine target file | Check if sources YAML already exists, decide create or append flow |
| 3 | Write sources YAML | Create full file, or only append missing traps/code_paths/omni_reference |
| 4 | Update INDEX.md | Append new model entry in the Sources section (skip if already exists) |
| 5 | Update LOG.md | Append adapt event record at the end |
| 6 | QRH candidate content review (optional) | Review operational issues encountered during this adaptation, propose QRH additions, wait for manual confirmation before writing |
| 7 | Knowledge-base consistency check | Run `kb-consistency` over sources YAML, INDEX, LOG, and placeholder status |

**Step Completion Protocol**:
- Each step completed → output `✓ Step N — <one-sentence result>`, then proceed to the next step
- Each step failed → output `✗ Step N — <root cause>`, enter HUMAN_NEEDED flow
- **Step 6 is optional**: When there are no candidate items, output `✓ Step 6 — No new QRH candidates`; when there are candidates, wait for manual confirmation; confirmation result does not affect overall `status`
- Step 7 is mandatory for Phase 6 pass. Phase 6 top-level `passed` is prohibited unless `validator.name == "kb-consistency"` and `validator.status == "passed"` in the latest iteration.

---

## Step 1: Read Adaptation Data

Read the structured extraction rules in:

```text
references/phases/phase6/extraction_rules.yaml
```

Use that file to extract base fields, infer `structural_tags`, collect `diff_components`, convert traps, build `code_paths`, and build `omni_reference`. It also defines model-category differences for LLM, VLM, and Diffusion, placeholder behavior when Phase 1 or Phase 2 has not passed, append-flow rules, and the source templates to use in Step 3.

Read structured data from Phase 0 v2 output:

**PRIMARY sources** (when `phase0_output.artifacts.hf_analysis_path` is present):
- From **hf_analysis.yaml**: `model_category`, `candidate_family`, `components` (key, diff, strategy, delta, structural_tags, hf_class), `traps`, `special_features`, `behavior_modifications`, `novel_modules`, `fp32_modules`
- From **bridge_mapping.yaml**: `component_bridge` (each entry: hf, megatron, strategy, confidence, behavioral_diff, delta), `gaps` (each entry: id, component, decision, impact, phase1_guidance)

**Legacy fallback** (when `phase0_output.artifacts.hf_analysis_path` is absent):
- From **model_spec.yaml**: `candidate_family`, `model_type`, `components`, `vlm_components`, `traps`, `special_features`, `behavior_modifications`

**Phase 1 file lists** (when phase1_output exists):
- `phase1_output.artifacts.generated_loongforge_files` -- LoongForge file paths for code_paths
- `phase1_output.artifacts.generated_megatron_files` -- Megatron file paths for megatron_code_paths (NEW)

When phase1_output exists but `generated_megatron_files` is absent (legacy Phase 1 output), fall back to `generated_files` for LoongForge paths and omit megatron_code_paths.

When using hf_analysis + bridge_mapping as primary sources:
- `traps` come from `hf_analysis.traps` (string list, same format as model_spec.traps)
- `special_features` come from `hf_analysis.special_features` (dict format, same as model_spec.special_features)
- Additional trap-like entries can be derived from `bridge_mapping.component_bridge[].behavioral_diff`: each behavioral_diff entry with `impact: high` or `impact: critical` becomes a trap entry with `field=topic` and `detail="HF: <hf> / Megatron: <megatron>"`.
- Deduplication: if a behavioral_diff topic overlaps with an existing trap `field`, prefer the existing trap entry.

When using model_spec.yaml as legacy fallback: traps extraction is unchanged from current behavior.

Step 1 is complete only when all fields required by the selected source template are either populated from Phase outputs/hf_analysis/bridge_mapping or explicitly represented by the placeholder rules from `extraction_rules.yaml`.

---

## Step 2: Determine Target File

```
target_path = knowledge_base/sources/<model_cat>/<family>.yaml
```

- If the file **does not exist** → execute Step 3 "create" flow
- If the file **already exists** → execute Step 3 "append" flow (do not overwrite existing content)

---

## Step 3: Write sources YAML

### Create Flow

Create the file from the model-category template under:

```text
references/phases/phase6/source_templates/llm.yaml
references/phases/phase6/source_templates/vlm.yaml
references/phases/phase6/source_templates/diffusion.yaml
```

Populate all template fields from Step 1. Preserve placeholder comments when Phase 1 or Phase 2 has not passed. If `traps` is empty, write `traps: []`.

Template selection:
- `model_cat == "llm"` -> `source_templates/llm.yaml`
- `model_cat == "vlm"` -> `source_templates/vlm.yaml`
- `model_cat == "diffusion"` -> `source_templates/diffusion.yaml`

### Append Flow (File Already Exists)

**Only append, do not modify existing content**. Check and supplement in the following order:

1. **code_paths section does not exist** → Insert complete `code_paths` section before the `traps` section using the template for `model_cat` (`LLM` / `VLM` / `Diffusion`)
2. **VLM and code_paths section exists but missing `encoder` field** → Append `encoder: <path>` at the end of the `code_paths` section (path from Step 1d; if phase1 did not pass, append `encoder: # Phase 1 not complete, to be supplemented`)
3. **omni_reference section does not exist** → Append complete `omni_reference` section at the end of the file using the template for `model_cat` (`LLM` / `VLM` / `Diffusion`)
4. **New traps (from Step 1c)** → Deduplicate and append to the end of the `traps` section
   - Deduplication rule: If a trap entry with the same `field` already exists, skip that entry
   - Append format consistent with existing entries

### Migration-Mode KB Updates

If the source YAML already declares `migration:` (i.e. this run was a reference-patchset migration), Phase 6 must keep that contract live and current:

1. Update `migration.reference_root`, `migration.reference_omni_path`, `migration.reference_megatron_path`, `migration.baseline_script`, `migration.lossdiff_bundle`, and `migration.lite_checkpoint` to match what Phase 0/3 actually used. If the reference root has rotated, bump these in place — do not duplicate the `migration:` block.
2. Reconcile `migration.forbidden_megatron_files` and `migration.forbidden_megatron_strings` with whatever the migration verifier actually rejected during Phase 1/3. If new strings were added to the verifier, mirror them here so future runs catch the same drift.
3. Reconcile `migration.allowed_megatron_diff.files` with the final Phase 3 `git diff --name-only` for the Megatron tree. Record any addition with a one-line `description` of why the diff is generic and default-off.
4. Update `validation.required_evidence` so that every gate the run actually needed is listed (random-init smoke, real-checkpoint smoke, same-batch lossdiff, migration verifier passing on the final tree). Do **not** drop evidence types just because a single run skipped them.
5. Never replace the `migration:` block with a generic Phase 6 template — the migration contract is the source of truth for whether this family can be reproduced from scratch in a later checkout.


---

## Step 4: Update INDEX.md

File path: `knowledge_base/INDEX.md`

1. Locate the corresponding category under `## Sources` section: `### LLM`, `### VLM`, or `### Diffusion` based on `model_cat`.
2. If the category heading does not exist, append the heading under `## Sources` before adding the entry.
3. Check if a `[<family>]` entry already exists.
4. **If not** → Append after the last line in that category:
   ```
   - [<family>](sources/<model_cat>/<family>.yaml) — <one-sentence architecture summary>
   ```
   One-sentence summary generation rule: List key features where `structural_tags` are true (e.g., `MLA+MoE+MTP`), then add a brief summary of the most important trap (no more than 20 characters). For diffusion models, summarize the primary diffusion/component tags from `model_spec.yaml`; if unavailable, write `Diffusion model adaptation reference`.
5. **If already exists** → Skip, output `Entry [<family>] already exists, skipped`

---

## Step 5: Update LOG.md

File path: `knowledge_base/LOG.md`

Append the following content at the **end** of the file (only append, do not modify existing entries):

```markdown
## [<YYYY-MM-DD>] adapt | <model_name>
- sources/<model_cat>/<family>.yaml: <created|appended (traps +N, code_paths <new|existing>, omni_reference <new|existing>)>
- Phase status: P0 ✅ / P1 <✅|❌|⚠️> / P2 <✅|❌|⚠️> / P3 <✅|❌|⚠️|–> / P4 <✅|❌|⚠️|–> / P5 <✅|❌|⚠️|–>
- Major diff components: <list component names with diff=differs, comma-separated; if none, write none>
- New traps count: <N>
```

Date format: `YYYY-MM-DD` (current system date).

Phase status symbol mapping:
- `passed` → `✅`
- `human_needed` → `❌`
- missing phase output file → `–`
- legacy `failed` → `❌`

`–` indicates that phase was not run (no corresponding output file).

---

## Step 6: QRH Candidate Content Review (Optional)

> **Goal**: Review **operational-level issues** encountered during this adaptation (GPU resources, environment variables, etc.). If there are new issues not covered by existing QRH, propose candidate content for manual confirmation before writing.

### 6a. Determine if there are QRH candidates

Check the following sources for **cross-model common operational issues**:

1. Whether any phase output has `failed` or retry records
2. Whether GPU/environment errors (OOM, NCCL timeout, ModuleNotFoundError, etc.) appeared in the current conversation context
3. The issue was ultimately resolved successfully (with reusable fix steps)

**QRH Candidate Criteria** (all must be satisfied):

| Condition | Description |
|------|------|
| Not model-specific | The issue is unrelated to model code/weights; any model could encounter it |
| Operational in nature | GPU resources, environment variables, dependency packages, network connectivity, and other infrastructure issues |
| Not covered by existing QRH | Comparing against existing documents under `knowledge_base/qrh/`, there is no corresponding entry |
| Has reusable fix steps | The fix method is clear and can be documented to guide subsequent agents |

If **no candidate content** → output `✓ Step 6 — No new QRH candidates`, done.

### 6b. Draft Candidate Content

If candidate content is found, output in the following format for manual review:

```
⚙️ QRH Candidate Content (pending manual confirmation)

Target file: knowledge_base/qrh/<filename>.md (create new)
        or: knowledge_base/qrh/<existing_filename>.md (append to "## Common Symptoms" or add new scenario section)

---
<Complete Markdown content draft>
---

Write to file? Please reply:
  - "Confirm write" → execute Step 6c
  - "Skip" or no reply → skip, Step 6 marked as skipped
```

> **Note**: Propose at most **1** QRH candidate at a time (prioritize the most impactful, most universal issue), to avoid accumulating too much content at once.

### 6c. Write QRH (executed after manual confirmation)

After receiving "Confirm write":

1. **Write file**:
   - Create new → create `knowledge_base/qrh/<filename>.md` with the draft content
   - Append → append content at the appropriate position in the existing file

2. **Update INDEX.md** QRH section (append entry at the end of the `## QRH` section):
   ```
   - [<filename without extension>](qrh/<filename>.md) — <one-sentence description of scenario and core operation>
   ```

3. **Update LOG.md**, append an `update` event:
   ```markdown
   ## [<YYYY-MM-DD>] update | QRH addition: <filename>
   - Created/Updated: knowledge_base/qrh/<filename>.md — <one-sentence description of new content>
   - Trigger source: <problem_type> encountered during <model_name> adaptation
   ```

4. Output `✓ Step 6 — Written qrh/<filename>.md and updated INDEX.md / LOG.md`

---

## Step 7: Knowledge-base consistency check

Run the `kb-consistency` validator after Step 6 completes or is skipped. This validator checks KB consistency only; it must not convert a failed or blocked adaptation into a passed adaptation.

Pass conditions:
- Target source YAML exists at `knowledge_base/sources/<model_cat>/<family>.yaml`
- `knowledge_base/INDEX.md` has the corresponding `[<family>](sources/<model_cat>/<family>.yaml)` entry
- `knowledge_base/LOG.md` has an adaptation event for `<model_name>` on the current date
- Source YAML contains or explicitly placeholders these sections: `hf_reference`, `structural_tags`, `code_paths`, `omni_reference`, `traps`
- If Phase 1 status is `passed`, `code_paths` must not remain a Phase 1 placeholder
- If Phase 2 status is `passed`, `omni_reference` must not remain a Phase 2 placeholder
- If Phase 3 or Phase 4 status is `passed`, the LOG phase status line must reflect that passed status
- If Phase 4 status is `passed`, `phase4_status` must be present in adaptation_status_source
- If Phase 5 status is `passed`, the LOG phase status line must reflect that passed status
- If Phase 1 status is `passed`, `megatron_code_paths` section must exist in the source YAML (in addition to `code_paths`)

If any check fails, repair the inconsistent file and rerun `kb-consistency`. If repair is blocked by file permissions or ambiguous source data, return `human_needed` with `validator.status="human_needed"`, `failure_gate="kb_consistency"`, evidence, artifacts/logs, and `fallback_phase=null`.

---

## Output Contract

Write `phase6_output.yml` to `run_dir/phases/phase6_output.yml`.

`phase6_output.yml` must follow the schema template in:

```text
references/phases/phase6/phase6_output_schema.yaml
```

The schema covers step-gate evidence, KB update status, full adaptation status source, model metadata, updated KB artifacts, consistency checks, and the authoritative `kb-consistency` validator result. Final `phase.status` remains `status: passed | human_needed`; `adaptation_final_status` may additionally be `incomplete` when earlier phase outputs are missing.

When Phase 0 v2 output exists, the output must include:
- `source.hf_analysis_path` -- path to the hf_analysis.yaml consumed
- `source.bridge_mapping_path` -- path to the bridge_mapping.yaml consumed
- `checks.bridge_mapping_consumed: true` -- confirms bridge_mapping was read
- `checks.hf_analysis_consumed: true` -- confirms hf_analysis was read

---

## Error Handling

| Situation | Handling |
|------|------|
| Phase 0 not completed | Immediately `human_needed` with `validator.status="human_needed"`, `failure_gate="phase0_prerequisite"`, evidence/artifacts/logs, and `fallback_phase="phase0"` |
| hf_path/config.json does not exist | Write `unknown` for `model_type` field, continue |
| hf_path/config.json top-level has no `vocab_size` (common for VLM, nested in `text_config`)| Read from `text_config.vocab_size` instead; if still failing, write `null # TODO: requires manual confirmation` |
| sources YAML write failure (file locked, etc.) | `human_needed`: provide complete YAML content for manual writing and set validator `failure_gate="source_yaml_write"`, `fallback_phase=null` |
| INDEX.md / LOG.md write failure | `human_needed`: provide append content for manual writing and set validator `failure_gate="index_or_log_write"`, `fallback_phase=null` |
| kb-consistency failed after repair attempt | `human_needed`: provide failed checks, artifacts/logs, and set `failure_gate="kb_consistency"`, `fallback_phase=null` |
| traps is empty (model_spec.yaml has no traps section) | Normal, write `traps: []` to file, continue |
| `ModuleNotFoundError` / missing environment variable | **First consult `knowledge_base/qrh/environment_setup.md`**, fix PYTHONPATH per module→path mapping then retry |
