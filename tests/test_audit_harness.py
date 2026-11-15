#!/usr/bin/env python3
"""Unit tests for the v2.0 public audit harness (zero external network calls)."""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import socketserver
import sys
import threading
import urllib.request
from pathlib import Path

import pytest
import yaml
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from local_receipt_proxy import _ThreadingHTTPServer, make_handler, strip_proprietary_fields
from render_step_summary import (
    aggregate_receipt_attestations,
    build_paired_samples_and_stats,
    check_no_secret_leak,
    mcnemar_exact,
    wilson_ci,
)
from resolve_audit_config import resolve_audit_config
from verify_ed25519_receipt import verify_jsonl_records, verify_receipt


def _build_signed_response(
    *,
    content: str = "ANSWER: C",
    zdr_enforced: object = True,
    cost_usd: object = 0,
    include_secret_recipe: bool = True,
) -> tuple[dict, str, str]:
    priv = Ed25519PrivateKey.generate()
    pub_pem = (
        priv.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
        .strip()
    )
    resp_sha = hashlib.sha256(content.encode("utf-8")).hexdigest()
    payload = {
        "schema": "big4.veritas.ed25519.v1",
        "request_id": "chatcmpl-test-001",
        "model_requested": "big4-ciclo5-free",
        "strict_free_only": True,
        "cost_usd": cost_usd,
        "zdr_enforced": zdr_enforced,
        "response_sha256": resp_sha,
    }
    if include_secret_recipe:
        payload["models_used"] = ["internal-secret-model-a", "internal-secret-model-b"]
        payload["pipeline_executed"] = "secret_cycle5_recipe"

    canonical_payload = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    payload_sha = hashlib.sha256(canonical_payload.encode("utf-8")).hexdigest()
    sig_b64 = base64.b64encode(priv.sign(canonical_payload.encode("utf-8"))).decode("ascii")

    response_obj = {
        "id": "chatcmpl-test-001",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": content}}],
        "veritas_receipt": {
            "seq": 9001,
            "signature": sig_b64,
            "public_key": pub_pem,
            "payload_sha256": payload_sha,
            "canonical_payload": canonical_payload,
            "payload": payload,
        },
    }
    if include_secret_recipe:
        response_obj["big4_ciclo5"] = {
            "models_used": ["internal-secret-model-a"],
            "pipeline_executed": "secret_cycle5_recipe",
            "consensus_type": "dual_agree",
        }
    return response_obj, pub_pem, content


def test_ed25519_verify_passes_and_strips_proprietary_recipe() -> None:
    resp, pub_pem, _ = _build_signed_response()
    res = verify_receipt(resp, pinned_pub_pem=pub_pem, require_zdr=True, require_zero_cost=True)
    assert res["ok"] is True
    assert res["zdr_enforced"] is True
    assert res["cost_usd"] == 0.0
    serialized = json.dumps(res)
    assert "models_used" not in serialized
    assert "pipeline_executed" not in serialized
    assert "consensus_type" not in serialized

    stripped = strip_proprietary_fields(resp)
    assert "big4_ciclo5" not in stripped
    assert "veritas_receipt" not in stripped


def test_ed25519_rejects_tamper_wrong_key_zdr_false_and_nonzero_cost() -> None:
    resp, pub_pem, _ = _build_signed_response(zdr_enforced=True, cost_usd=0)
    with pytest.raises(ValueError, match="response_sha256 mismatch"):
        verify_receipt(resp, pinned_pub_pem=pub_pem, response_text_override="ANSWER: A")

    other_pub = (
        Ed25519PrivateKey.generate()
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode("utf-8")
    )
    with pytest.raises(ValueError, match="Pinned public key"):
        verify_receipt(resp, pinned_pub_pem=other_pub)

    resp_no_zdr, pub_no_zdr, _ = _build_signed_response(zdr_enforced=False, cost_usd=0)
    assert verify_receipt(resp_no_zdr, pinned_pub_pem=pub_no_zdr)["zdr_enforced"] is False
    with pytest.raises(ValueError, match="ZDR policy check"):
        verify_receipt(resp_no_zdr, pinned_pub_pem=pub_no_zdr, require_zdr=True)

    resp_cost, pub_cost, _ = _build_signed_response(zdr_enforced=True, cost_usd=0.05)
    with pytest.raises(ValueError, match="zero-cost policy check"):
        verify_receipt(resp_cost, pinned_pub_pem=pub_cost, require_zero_cost=True)


def test_local_receipt_proxy_captures_receipt_and_strips_recipes(tmp_path: Path) -> None:
    resp, pub_pem, _ = _build_signed_response(zdr_enforced=True, cost_usd=0)

    class _FakeUpstream(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_POST(self) -> None:
            body = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    upstream = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _FakeUpstream)
    up_port = upstream.server_address[1]
    t_up = threading.Thread(target=upstream.serve_forever, daemon=True)
    t_up.start()

    log_file = tmp_path / "receipts.jsonl"
    handler = make_handler(
        upstream_base=f"http://127.0.0.1:{up_port}/v1",
        pinned_pem=pub_pem,
        receipt_log_path=str(log_file),
        require_zdr=True,
        require_zero_cost=True,
    )
    proxy = _ThreadingHTTPServer(("127.0.0.1", 0), handler)
    px_port = proxy.server_address[1]
    t_px = threading.Thread(target=proxy.serve_forever, daemon=True)
    t_px.start()

    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{px_port}/v1/chat/completions",
            data=json.dumps({"model": "big4-ciclo5-free", "messages": [{"role": "user", "content": "hi"}]}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer dummy"},
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            returned = json.loads(r.read().decode("utf-8"))
        assert returned["choices"][0]["message"]["content"] == "ANSWER: C"
        assert "big4_ciclo5" not in returned
        assert "veritas_receipt" not in returned
        assert "models_used" not in json.dumps(returned)

        rep = verify_jsonl_records(str(log_file), pub_pem, require_zdr=True, require_zero_cost=True)
        assert rep["verified_count"] == 1
        assert "models_used" not in json.dumps(rep)
        assert "pipeline_executed" not in json.dumps(rep)
    finally:
        proxy.shutdown()
        proxy.server_close()
        upstream.shutdown()
        upstream.server_close()


def test_summary_receipt_aggregation_and_paired_samples() -> None:
    empty_agg = aggregate_receipt_attestations({"receipts": [], "verified_count": 0, "probe_count": 0})
    assert empty_agg["vendor_attested_zdr_all_true"] is None
    assert empty_agg["vendor_attested_max_cost_usd"] is None

    mixed_agg = aggregate_receipt_attestations(
        {
            "source": "live_benchmark_proxy_capture",
            "verified_count": 2,
            "probe_count": 2,
            "receipts": [
                {"ok": True, "zdr_enforced": True, "cost_usd": 0.0},
                {"ok": True, "zdr_enforced": False, "cost_usd": 0.04},
            ],
        }
    )
    assert mixed_agg["vendor_attested_zdr_all_true"] is False
    assert mixed_agg["vendor_attested_max_cost_usd"] == 0.04

    arm_a = {("mmlu_pro", "q1"): {"task": "mmlu_pro", "sample_id": "q1", "correct": False, "answer_sha256_prefix": "aaa"}}
    arm_b = {("mmlu_pro", "q1"): {"task": "mmlu_pro", "sample_id": "q1", "correct": True, "answer_sha256_prefix": "bbb"}}
    rows, by_task, overall = build_paired_samples_and_stats(arm_a, arm_b, ["mmlu_pro"])
    assert len(rows) == 1
    assert by_task["mmlu_pro"]["arm_b_only_correct"] == 1
    assert overall["delta_pp"] == 100.0


def test_check_no_secret_leak_blocks_credentials_and_recipes() -> None:
    check_no_secret_leak('{"status":"ok","url":"https://api.big4.cloud/v1"}')
    for bad in (
        "bearer sk-big4-abc1234567890",
        "key=sk-or-v1-abc1234567890",
        "x|byt:openrouter|token",
        '{"models_used": ["a"]}',
        '{"pipeline_executed": "hybrid_verified_solver:c1"}',
    ):
        with pytest.raises(RuntimeError):
            check_no_secret_leak(bad)


def test_mcnemar_exact_and_wilson_ci() -> None:
    pairs = [(True, True)] * 20 + [(False, True)] * 10 + [(True, False)] * 2 + [(False, False)] * 8
    stat = mcnemar_exact(pairs)
    assert stat["paired_items"] == 40
    assert abs(stat["exact_two_sided_p"] - 0.038574) < 1e-5
    assert stat["delta_pp"] == 20.0

    tied = mcnemar_exact([(True, False)] * 5 + [(False, True)] * 5)
    assert tied["exact_two_sided_p"] == 1.0

    ci = wilson_ci(320, 400)
    assert 75.5 <= ci["low_pct"] <= 76.2
    assert 83.4 <= ci["high_pct"] <= 84.0


def test_humaneval_docker_compose_is_airgapped_and_credential_free() -> None:
    compose_path = REPO_ROOT / "docker" / "humaneval-compose.yaml"
    data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    svc = data["services"]["default"]
    assert svc["network_mode"] == "none"
    assert "ALL" in svc["cap_drop"]
    assert "no-new-privileges:true" in svc["security_opt"]
    assert "environment" not in svc
    assert "env_file" not in svc


def test_resolve_audit_config_decouples_arm_a_and_generates_random_seed() -> None:
    cfg_direct = resolve_audit_config(
        audit_mode="free_big4_vs_direct_provider",
        target_model="google/gemma-4-31b-it",
        byt_provider="auto",
        sample_seed="random",
        big4_api_key="sk-big4-dummy-audit-token-1234",
        byt_api_key="sk-or-v1-dummy-disposable-key",
    )
    assert cfg_direct["ARM_A_INDEPENDENT"] == "true"
    assert cfg_direct["UPSTREAM_BASE_URL"] == "https://openrouter.ai/api/v1"
    assert cfg_direct["ARM_A_INSPECT_MODEL"] == "openai-api/upstream/google/gemma-4-31b-it"
    assert cfg_direct["ARM_B_USES_BYT"] == "false"
    assert int(cfg_direct["SAMPLE_SEED"]) >= 100_000_000

    cfg_boost = resolve_audit_config(
        audit_mode="byt_model_boost",
        target_model="anthropic/claude-sonnet-4.6",
        byt_provider="openrouter",
        sample_seed="777",
        big4_api_key="sk-big4-dummy-audit-token-1234",
        byt_api_key="sk-or-v1-dummy-disposable-key",
    )
    assert cfg_boost["ARM_A_INDEPENDENT"] == "true"
    assert cfg_boost["ARM_A_INSPECT_MODEL"] == "openai-api/upstream/anthropic/claude-sonnet-4.6"
    assert cfg_boost["ARM_B_MODEL"] == "big4-ciclo5-byt:anthropic/claude-sonnet-4.6"
    assert cfg_boost["ARM_B_USES_BYT"] == "true"
    assert cfg_boost["SAMPLE_SEED"] == "777"
