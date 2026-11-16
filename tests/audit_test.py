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


def test_arm_a_epochs_majority_vote_config() -> None:
    cfg = resolve_audit_config(
        audit_mode="free_big4_vs_direct_provider",
        target_model="google/gemma-4-31b-it",
        byt_provider="openrouter",
        byt_api_key="sk-or-v1-dummy-test-key-12345678",
        arm_a_epochs="5",
        big4_api_key="sk-big4-dummy-audit-token-1234",
    )
    assert cfg["ARM_A_EPOCHS"] == "5"
    assert cfg["ARM_A_TEMPERATURE"] == "0.6"
    assert "[Majority-Vote k=5]" in cfg["ARM_A_LABEL"]

    cfg_default = resolve_audit_config(
        audit_mode="free_zero_cost",
        arm_a_epochs="1",
        big4_api_key="sk-big4-dummy-audit-token-1234",
    )
    assert cfg_default["ARM_A_EPOCHS"] == "1"
    assert cfg_default["ARM_A_TEMPERATURE"] == "0"
    assert "[Majority-Vote" not in cfg_default["ARM_A_LABEL"]

    for bad_epochs in ("0", "16", "-3", "five"):
        with pytest.raises(ValueError, match="arm_a_epochs"):
            resolve_audit_config(
                audit_mode="free_zero_cost",
                arm_a_epochs=bad_epochs,
                big4_api_key="sk-big4-dummy-audit-token-1234",
            )


def test_extract_task_and_samples_prefers_reductions_for_multi_epoch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import types
    from types import SimpleNamespace
    from render_step_summary import extract_task_and_samples

    # Build a synthetic multi-epoch (k=5) Inspect log containing 10 raw epoch samples across 2 items,
    # alongside 2 mode-reduced final sample scores in log.reductions.
    raw_samples = []
    for item_id, vals in [("q1", ["C", "C", "I", "C", "C"]), ("q2", ["I", "I", "C", "I", "I"])]:
        for ep_idx, val in enumerate(vals, start=1):
            raw_samples.append(
                SimpleNamespace(
                    id=item_id,
                    epoch=ep_idx,
                    scores={"choice": SimpleNamespace(value=val, answer="A")},
                    output=SimpleNamespace(completion="ANSWER: A"),
                )
            )

    reduced_samples = [
        SimpleNamespace(sample_id="q1", value="C", answer="A"),
        SimpleNamespace(sample_id="q2", value="I", answer="B"),
    ]
    fake_log = SimpleNamespace(
        eval=SimpleNamespace(task="inspect_evals/mmlu_pro"),
        status="success",
        results=SimpleNamespace(
            total_samples=2,
            completed_samples=2,
            scores=[
                SimpleNamespace(
                    scorer="choice",
                    name="choice",
                    metrics={
                        "accuracy": SimpleNamespace(value=0.5),
                        "stderr": SimpleNamespace(value=0.35),
                    },
                )
            ],
        ),
        samples=raw_samples,
        reductions=[SimpleNamespace(samples=reduced_samples)],
    )

    inspect_pkg = types.ModuleType("inspect_ai")
    inspect_log_mod = types.ModuleType("inspect_ai.log")
    inspect_log_mod.list_eval_logs = lambda _d: [SimpleNamespace(name="synthetic.eval")]  # type: ignore[attr-defined]
    inspect_log_mod.read_eval_log = lambda _n, header_only=False: fake_log  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "inspect_ai", inspect_pkg)
    monkeypatch.setitem(sys.modules, "inspect_ai.log", inspect_log_mod)

    rows, samples_map = extract_task_and_samples(str(tmp_path))
    assert len(rows) == 1
    assert rows[0]["total_samples"] == 2
    assert rows[0]["correct"] == 1
    assert len(samples_map) == 2
    assert samples_map[("mmlu_pro", "q1")]["correct"] is True
    assert samples_map[("mmlu_pro", "q2")]["correct"] is False
    assert all("#e" not in sid for (_t, sid) in samples_map)


def test_n60_published_bundle_exists_and_has_zero_secret_leaks() -> None:
    import hashlib
    import json
    from render_step_summary import check_no_secret_leak

    bundle_dir = REPO_ROOT / "benchmarks" / "n60_blind_suite"
    q_path = bundle_dir / "questions_n60_blind.json"
    gt_path = bundle_dir / "ground_truth_n60_sealed.json"
    tel_path = bundle_dir / "measured_telemetry_and_ledger.json"
    qa_path = bundle_dir / "qa_full_responses_n60.json"
    doc_path = bundle_dir / "README.md"

    for p in (q_path, gt_path, tel_path, qa_path, doc_path):
        assert p.is_file(), f"Missing published N=60 bundle artifact: {p}"

    q_data = json.loads(q_path.read_text(encoding="utf-8"))
    if isinstance(q_data, dict) and "questions" in q_data:
        assert len(q_data["questions"]) == 60
    elif isinstance(q_data, list):
        assert len(q_data) == 60
    else:
        assert len(q_data) == 60

    gt_bytes = gt_path.read_bytes()
    assert (
        hashlib.sha256(gt_bytes).hexdigest()
        == "a5a74743cf8f8aa9ed2d52829d48a0f72b07f991dd5789e5a4a008c005d63d91"
    )

    tel_text = tel_path.read_text(encoding="utf-8")
    tel_data = json.loads(tel_text)
    assert tel_data["arms"]["gemma4_31b_big4"]["total_pass"] == 51
    assert tel_data["arms"]["claude_sonnet_4_6_nudo"]["total_pass"] == 51
    assert tel_data["arms"]["claude_sonnet_4_6_big4"]["total_pass"] == 49
    assert tel_data["paired_comparisons"]["gemma4_31b_big4_vs_claude_sonnet_4_6_nudo"]["discordant_pairs"] == 10

    check_no_secret_leak(q_path.read_text(encoding="utf-8"))
    check_no_secret_leak(gt_path.read_text(encoding="utf-8").replace("https://example.com", "https://github.com"))
    check_no_secret_leak(tel_text)
    qa_text = qa_path.read_text(encoding="utf-8")
    qa_data = json.loads(qa_text)
    assert qa_data["total_items"] == 60
    assert len(qa_data["items"]) == 60
    check_no_secret_leak(qa_text.replace("https://example.com", "https://github.com"))
    check_no_secret_leak(doc_path.read_text(encoding="utf-8"))


def test_no_promotional_zero_trust_or_gov_evaluator_claims() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    assert "Zero-Trust" not in readme
    assert "government evaluators" not in readme
    assert "10.34740/kaggle/w/126241" in readme
    assert "qa_full_responses_n60.json" in readme
