"""Tests for skills.adapt.lib.redact — secret redactor with residual post-check."""
from __future__ import annotations

from skills.adapt.lib.redact import redact, RedactionResult


# ---------------------------------------------------------------------------
# Individual pattern tests
# ---------------------------------------------------------------------------

def test_bearer_header():
    result = redact("Bearer abc123def456ghi789jkl")
    assert result.cleaned == "[REDACTED:bearer_header]"
    assert result.accept is True


def test_github_pat_v1():
    result = redact("token=ghp_1234567890ABCDEFGHIJ")
    assert "[REDACTED:github_pat_v1]" in result.cleaned
    assert result.accept is True


def test_hf_token():
    result = redact("hf_AAAAAAAAAAAAAAAAAAAAAA")
    assert result.cleaned == "[REDACTED:hf_token]"
    assert result.accept is True


def test_aws_access_key():
    result = redact("aws=AKIAIOSFODNN7EXAMPLE other=AKIA1234567890ABCDEF")
    assert result.cleaned.count("[REDACTED:aws_access_key]") == 2
    # Check matches reports both
    match_names = [name for name, count in result.matches]
    assert "aws_access_key" in match_names
    assert result.accept is True


def test_home_path():
    result = redact("/home/alice/secret.txt")
    assert "[REDACTED:home_path]" in result.cleaned
    assert result.accept is True


def test_plain_text_no_secrets():
    text = "plain text no secrets"
    result = redact(text)
    assert result.cleaned == text
    assert result.matches == []
    assert result.accept is True


# ---------------------------------------------------------------------------
# Residual / adversarial tests
# ---------------------------------------------------------------------------

def test_no_residual_after_redaction():
    """After redaction of a real pattern, no residual ghp_ should survive."""
    result = redact("ghp_AAAAAAAAAAAAAAAAAAAA then ghp_BBBBBBBBBBBBBBBBBBBB")
    assert result.accept is True
    # Both ghp_ patterns should be fully replaced
    assert "ghp_" not in result.cleaned
    assert result.cleaned.count("[REDACTED:github_pat_v1]") == 2


def test_redaction_marker_not_triggered_as_residual():
    """The [REDACTED:...] markers themselves should not trigger residual detection."""
    result = redact("ghp_AAAAAAAAAAAAAAAAAAAA")
    # The cleaned text contains "[REDACTED:github_pat_v1]" which should NOT
    # trigger any pattern match in the residual scan.
    assert result.accept is True


# ---------------------------------------------------------------------------
# Multi-pattern corpus test
# ---------------------------------------------------------------------------

def test_all_secrets_in_one_corpus():
    corpus = (
        "Authorization: Bearer abcdef1234567890XYZ\n"
        "GH_TOKEN=ghp_AAAAAAAAAAAAAAAAAAAA\n"
        "PAT=github_pat_BBBBBBBBBBBBBBBBBBBB\n"
        "HF=hf_CCCCCCCCCCCCCCCCCCCC\n"
        "AWS=AKIAIOSFODNN7EXAMPLE\n"
        "PATH=/home/alice/secret\n"
    )
    result = redact(corpus)
    assert result.accept is True
    assert "[REDACTED:bearer_header]" in result.cleaned
    assert "[REDACTED:github_pat_v1]" in result.cleaned
    assert "[REDACTED:github_pat_v2]" in result.cleaned
    assert "[REDACTED:hf_token]" in result.cleaned
    assert "[REDACTED:aws_access_key]" in result.cleaned
    assert "[REDACTED:home_path]" in result.cleaned


# ---------------------------------------------------------------------------
# Internal domains test
# ---------------------------------------------------------------------------

def test_internal_domains():
    result = redact("internal.example.corp", internal_domains=("internal.example.corp",))
    assert result.cleaned == "[REDACTED:internal_domain]"
    assert result.accept is True


def test_internal_domains_not_triggered_by_default():
    result = redact("internal.example.corp")
    # Without internal_domains, the text is unchanged
    assert result.cleaned == "internal.example.corp"
    assert result.accept is True


# ---------------------------------------------------------------------------
# Additional pattern coverage
# ---------------------------------------------------------------------------

def test_github_oauth():
    result = redact("gho_AAAAAAAAAAAAAAAAAAAA")
    assert "[REDACTED:github_oauth]" in result.cleaned
    assert result.accept is True


def test_github_user():
    result = redact("ghu_AAAAAAAAAAAAAAAAAAAA")
    assert "[REDACTED:github_user]" in result.cleaned
    assert result.accept is True


def test_github_server():
    result = redact("ghs_AAAAAAAAAAAAAAAAAAAA")
    assert "[REDACTED:github_server]" in result.cleaned
    assert result.accept is True


def test_aws_secret_kv():
    result = redact("aws_secret_access_key=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcd")
    assert "[REDACTED:aws_secret_kv]" in result.cleaned
    assert result.accept is True
