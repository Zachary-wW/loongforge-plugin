"""Secret redactor — regex sweep with residual post-check.

Strips ghp_, github_pat_, hf_, AKIA, Bearer, /home/<user>/, gho_, ghu_, ghs_,
aws_secret_access_key from text and returns accept=False if any pattern survives.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Order matters: longer/more-specific patterns FIRST so they win over shorter ones.
# All patterns are case-sensitive unless noted.
_SECRET_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    ("github_pat_v2",  re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("github_pat_v1",  re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("github_oauth",   re.compile(r"gho_[A-Za-z0-9]{20,}")),
    ("github_user",    re.compile(r"ghu_[A-Za-z0-9]{20,}")),
    ("github_server",  re.compile(r"ghs_[A-Za-z0-9]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("hf_token",       re.compile(r"hf_[A-Za-z0-9]{20,}")),
    ("bearer_header",  re.compile(r"Bearer\s+[A-Za-z0-9._\-+/]{16,}")),
    ("home_path",      re.compile(r"/home/[a-zA-Z0-9_\-\.]+(/|$)")),
    ("aws_secret_kv",  re.compile(r"(?i)aws_secret(_access)?_key\s*[:=]\s*[A-Za-z0-9/+=]{30,}")),
)

# Internal-domain list lives in a YAML config so ops can extend without code change.
_INTERNAL_DOMAIN_CONFIG = "skills/adapt/knowledge_base/redact_domains.yml"


@dataclass(frozen=True)
class RedactionResult:
    cleaned: str
    matches: list[tuple[str, int]]   # [(pattern_name, count), ...]
    accept: bool                      # False = there is at least one residual hit after redaction


def redact(text: str, *, internal_domains: tuple[str, ...] = ()) -> RedactionResult:
    """Replace each match with '[REDACTED:<name>]'. Re-run a sanity grep after
    replacement; if any pattern still matches, return accept=False so the caller
    refuses to post."""
    cleaned = text
    counts: dict[str, int] = {}
    for name, pat in _SECRET_PATTERNS:
        cleaned, n = pat.subn(f"[REDACTED:{name}]", cleaned)
        if n:
            counts[name] = n
    for dom in internal_domains:
        pat = re.compile(re.escape(dom))
        cleaned, n = pat.subn("[REDACTED:internal_domain]", cleaned)
        if n:
            counts.setdefault("internal_domain", 0)
            counts["internal_domain"] += n
    # Post-check: residual scan
    residual = any(p.search(cleaned) for _, p in _SECRET_PATTERNS)
    return RedactionResult(cleaned=cleaned, matches=list(counts.items()), accept=not residual)
