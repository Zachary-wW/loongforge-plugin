"""Preflight checks for loop-engineering startup. Fails fast with a precise,
ordered, human-readable error block; on dry_run=True, skips live-write probes
but still validates URL shape and gh auth status."""
from __future__ import annotations

import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from skills.adapt.lib.schema import ReposBlock
    from skills.adapt.lib.gh_client import GhClient


@dataclass
class PreflightResult:
    """Result of a preflight check run.

    ok=True means all checks passed (failures is empty).
    warnings carry informational items that don't block startup.
    branch_protection carries raw gh api output for record.
    """
    ok: bool
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)   # W4: branch-protection warn-only items
    branch_protection: dict = field(default_factory=dict)


def _owner_repo_from_url(url: str) -> str:
    """Extract '<owner>/<repo>' from a https://github.com/<owner>/<repo>(.git)? URL."""
    from urllib.parse import urlparse
    p = urlparse(str(url)).path.strip("/")
    if p.endswith(".git"):
        p = p[:-4]
    parts = p.split("/")
    if len(parts) < 2:
        return p
    return f"{parts[0]}/{parts[1]}"


def _check_branch_protection_compatible(prot: dict) -> tuple[list[str], list[str]]:
    """Return (fail_reasons, warnings).

    Hard-fail (fail_reasons) -- auto-merge cannot satisfy these without a
    Phase 2 allowlist override (deferred):
      - required_pull_request_reviews.required_approving_review_count > 0
      - restrictions present and non-empty (push allowlist locks out the bot)
      - lock_branch == True (no commits allowed at all)

    Warn-only (Phase 1 informational; Phase 2 must satisfy):
      - required_status_checks.contexts non-empty (Phase 2 CI must pass them)
      - enforce_admins == True (informational; affects who can merge)
      - required_linear_history == True (informational; affects merge strategy)

    Empty dict (no protection) = compatible, no warnings."""
    fail_reasons: list[str] = []
    warnings: list[str] = []
    if not prot:
        return fail_reasons, warnings

    required = prot.get("required_pull_request_reviews") or {}
    n = required.get("required_approving_review_count", 0)
    if n and n > 0:
        fail_reasons.append(
            f"requires {n} approving review(s) (loop auto-merge incompatible)"
        )

    # restrictions: GH returns {"users": [...], "teams": [...], "apps": [...]}
    # when set; empty/missing means no restriction. Non-empty = hard fail.
    restrictions = prot.get("restrictions") or {}
    if restrictions:
        users = restrictions.get("users") or []
        teams = restrictions.get("teams") or []
        apps = restrictions.get("apps") or []
        if users or teams or apps:
            fail_reasons.append(
                f"push restrictions allowlist non-empty "
                f"(users={len(users)}, teams={len(teams)}, apps={len(apps)}); "
                f"loop bot is not in allowlist (Phase 2 will add --allowlist-override)"
            )

    if prot.get("lock_branch") is True:
        fail_reasons.append(
            "lock_branch=true (branch is fully locked; no commits allowed)"
        )

    rsc = prot.get("required_status_checks") or {}
    contexts = rsc.get("contexts") or []
    if contexts:
        warnings.append(
            f"required_status_checks.contexts={contexts!r} "
            f"(Phase 1 warn-only; Phase 2 CI must satisfy these)"
        )

    if prot.get("enforce_admins") is True:
        warnings.append(
            "enforce_admins=true (informational; admins also subject to protection)"
        )

    if prot.get("required_linear_history") is True:
        warnings.append(
            "required_linear_history=true (informational; Phase 2 merge strategy "
            "must use squash/rebase, not merge-commit)"
        )

    return fail_reasons, warnings


def run_preflight(repos: "ReposBlock", *, dry_run: bool, gh: "GhClient") -> PreflightResult:
    """Run all preflight checks.

    dry_run=True skips live-write probes (repo_permissions, branch_protection)
    but still calls auth_status and repo_view. Network failures (ckpt URL
    unreachable) are tolerated in dry_run mode.
    """
    failures: list[str] = []
    warnings_list: list[str] = []   # W4: branch-protection warn-only items
    branch_protection_record: dict = {}

    # 1. gh auth status -- always run, even in dry_run
    auth = gh.auth_status()
    if auth.returncode != 0:
        failures.append("gh_auth_status: not logged in (run `gh auth login`)")

    # 2. For each external repo, check read perm + (live mode only) write perm + branch protection
    for label, spec in (("loongforge", repos.loongforge), ("megatron", repos.megatron)):
        owner_repo = _owner_repo_from_url(str(spec.url))
        rv = gh.repo_view(owner_repo)
        if rv.returncode != 0:
            failures.append(f"{label}_read: cannot read {owner_repo}")
            continue
        if not dry_run:
            perms = gh.repo_permissions(owner_repo)
            if not perms.get("push"):
                failures.append(f"{label}_write: missing push permission on {owner_repo}")
            prot = gh.branch_protection(owner_repo, spec.base_ref)
            branch_protection_record[owner_repo] = prot
            fail_reasons, warns = _check_branch_protection_compatible(prot)
            for fr in fail_reasons:
                failures.append(
                    f"branch_protection: {owner_repo}:{spec.base_ref} {fr}"
                )
            for w in warns:
                warnings_list.append(
                    f"branch_protection: {owner_repo}:{spec.base_ref} {w}"
                )

    # 3. HF impl URL reachable (gh api on the github repo)
    impl_owner_repo = _owner_repo_from_url(str(repos.hf_impl.url))
    if "/" in impl_owner_repo:
        impl_rv = gh.repo_view(impl_owner_repo)
        if impl_rv.returncode != 0:
            failures.append(f"hf_impl_read: cannot read {impl_owner_repo}")

    # 4. ckpt URL reachable -- HEAD probe to https://huggingface.co/api/models/<org>/<model>
    #    Always run (read-only) unless we cannot reach the network at all.
    try:
        ckpt_url = str(repos.hf_ckpt.url)
        from urllib.parse import urlparse as _urlparse
        p = _urlparse(ckpt_url)
        api_url = ckpt_url
        if p.netloc == "huggingface.co":
            path = p.path.strip("/")
            if path.count("/") >= 1:
                api_url = f"https://huggingface.co/api/models/{path}"
        req = urllib.request.Request(api_url, method="HEAD")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 400:
                failures.append(f"hf_ckpt_unreachable: HTTP {resp.status} on {api_url}")
    except (urllib.error.URLError, OSError) as e:
        # Don't fail dry_run for unreachable network (matches RESEARCH 4 dry-run path).
        if not dry_run:
            failures.append(f"hf_ckpt_unreachable: {type(e).__name__} on {ckpt_url}")

    return PreflightResult(
        ok=not failures,
        failures=failures,
        warnings=warnings_list,
        branch_protection=branch_protection_record,
    )


def format_failures(result: PreflightResult) -> str:
    """Render the canonical fail-fast error block.

    W4: also renders warnings (warn-only branch-protection items) when present,
    even when ok=True (warnings are informational, do not block)."""
    lines: list[str] = []
    if not result.ok:
        lines.append("PREFLIGHT FAILED:")
        for f in result.failures:
            lines.append(f"  - {f}")
    if result.warnings:
        if lines:
            lines.append("")
        lines.append("PREFLIGHT WARNINGS (informational):")
        for w in result.warnings:
            lines.append(f"  - {w}")
    if not result.ok:
        lines.append("Aborting. Re-run with --dry-run to bypass live-write probes.")
    return "\n".join(lines)
