#!/usr/bin/env python3
"""Contract and documentation regression checks for the Big4 v2.0 public audit repo."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
TESTS_DIR = REPO_ROOT / "tests"
for p in (SCRIPTS_DIR, TESTS_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Re-export core harness tests so `pytest tests/audit_test.py` runs the full verification suite.
from local_receipt_proxy import validate_upstream_base_url
from render_step_summary import wilson_ci
from resolve_audit_config import resolve_audit_config
from test_audit_harness import (  # noqa: F401
    test_check_no_secret_leak_blocks_credentials_and_recipes,
    test_ed25519_rejects_tamper_wrong_key_zdr_false_and_nonzero_cost,
    test_ed25519_verify_passes_and_strips_proprietary_recipe,
    test_humaneval_docker_compose_is_airgapped_and_credential_free,
    test_local_receipt_proxy_captures_receipt_and_strips_recipes,
    test_mcnemar_exact_and_wilson_ci,
    test_resolve_audit_config_decouples_arm_a_and_generates_random_seed,
    test_summary_receipt_aggregation_and_paired_samples,
)


def test_readme_clarifies_external_apis_gemma4_vps_and_proof_limits() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Gemma 4 31B" in readme
    assert "google/gemma-4-31b-it" in readme
    assert "Claude Sonnet 4.6" in readme
    assert "25/month" in readme
    assert "104.207.84.209" in readme
    assert "neither affiliated with nor endorsed by the UK AI Safety Institute" in readme
    assert "What `Ed25519` Receipts Do — and Do Not — Prove" in readme


def test_workflow_yaml_parses_cleanly_and_uses_airgapped_humaneval() -> None:
    wf_text = (REPO_ROOT / ".github" / "workflows" / "uk-aisi-public-audit.yml").read_text(encoding="utf-8")
    # Ensure no parenthesized GitHub Actions expressions in ${{ ... }}
    expr_matches = re.findall(r"\$\{\{.*?\}\}", wf_text, flags=re.S)
    for expr in expr_matches:
        assert "(" not in expr and ")" not in expr, f"Unexpected parentheses in GH Actions expression: {expr}"

    wf = yaml.safe_load(wf_text)
    steps = wf["jobs"]["uk-aisi-inspect-audit"]["steps"]
    step_text = "\n".join(str(s.get("run", "")) for s in steps)
    assert "pytest" in step_text
    assert step_text.count("inspect eval inspect_evals/humaneval --sandbox docker:docker/humaneval-compose.yaml") == 2
    assert "unset BIG4_API_KEY BIG4_BASE_URL" in step_text
    assert "unset BYT_API_KEY" in step_text


def test_hardening_guards_ssrf_path_traversal_and_wilson_clamping() -> None:
    assert validate_upstream_base_url("https://104-207-84-209.sslip.io/v1").scheme == "https"
    assert validate_upstream_base_url("http://127.0.0.1:8080/v1").hostname == "127.0.0.1"
    for bad_url in ("http://169.254.169.254/latest", "file:///etc/passwd", "http://evil.example/v1"):
        with pytest.raises(ValueError):
            validate_upstream_base_url(bad_url)

    for bad_path in ("/etc/passwd", "../secrets.jsonl", "foo/../../bar.jsonl"):
        with pytest.raises(ValueError, match="relative path"):
            resolve_audit_config(
                audit_mode="free_zero_cost",
                custom_holdout_jsonl=bad_path,
                big4_api_key="sk-big4-dummy-audit-token-1234",
            )

    clamped = wilson_ci(120, 100)
    assert clamped["high_pct"] == 100.0 and clamped["low_pct"] > 90.0
