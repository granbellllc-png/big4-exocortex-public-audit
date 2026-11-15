#!/usr/bin/env python3
"""
Standalone Offline Ed25519 Receipt Verifier for OpenAI-Compatible Audit Responses.

Cryptographic scope (stated transparently):
  1. SHA-256(choices[0].message.content) == veritas_receipt.payload.response_sha256
  2. SHA-256(veritas_receipt.canonical_payload) == veritas_receipt.payload_sha256
  3. JSON parity between canonical_payload and payload
  4. Pinned public key match (--public-key <pem_file>)
  5. Cryptographic Ed25519 signature verification over UTF-8 canonical_payload bytes
  6. Optional strict assertions on signed metadata (--require-zdr, --require-zero-cost)

Note: An Ed25519 receipt proves payload integrity and signed non-repudiation of the
metadata declared by the server; it is not an independent hardware attestation of
remote RAM erasure or third-party upstream provider billing.

All proprietary routing/model-mix fields (`models_used`, `pipeline_executed`,
`consensus_type`) are stripped from verifier outputs.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from typing import Any, Dict, List, Optional


PROBE_PROMPTS = [
    "Which planet is the third from the Sun?\nA) Venus\nB) Earth\nC) Mars\nD) Jupiter\nReply with 'ANSWER: <LETTER>'.",
    "What is 15 * 12?\nA) 160\nB) 170\nC) 180\nD) 190\nReply with 'ANSWER: <LETTER>'.",
    "Which chemical element has atomic number 8?\nA) Nitrogen\nB) Oxygen\nC) Carbon\nD) Neon\nReply with 'ANSWER: <LETTER>'.",
    "What is the time complexity of binary search on a sorted array of size n?\nA) O(n)\nB) O(n log n)\nC) O(log n)\nD) O(1)\nReply with 'ANSWER: <LETTER>'.",
    "In Python, which keyword defines an anonymous inline function?\nA) def\nB) func\nC) lambda\nD) yield\nReply with 'ANSWER: <LETTER>'.",
]


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_public_key_pem(path: str) -> str:
    with open(path.strip(), "r", encoding="utf-8") as fh:
        raw = fh.read().strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and parsed.get("public_key_pem"):
            return str(parsed["public_key_pem"]).strip()
    except json.JSONDecodeError:
        pass
    return raw


def verify_ed25519_signature(pub_pem: str, sig_b64: str, message_bytes: bytes) -> str:
    sig_bytes = base64.b64decode(sig_b64, validate=True)

    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        pub = load_pem_public_key(pub_pem.encode("utf-8"))
        if not isinstance(pub, Ed25519PublicKey):
            raise ValueError(f"Expected Ed25519 public key, got {type(pub).__name__}")
        pub.verify(sig_bytes, message_bytes)
        return "python-cryptography"
    except ImportError:
        pass

    openssl_bin = shutil.which("openssl")
    if not openssl_bin:
        raise RuntimeError("Neither Python 'cryptography' package nor 'openssl' CLI is installed")

    with tempfile.TemporaryDirectory(prefix="ed25519_verify_") as tmp:
        pub_path = os.path.join(tmp, "pub.pem")
        msg_path = os.path.join(tmp, "msg.bin")
        sig_path = os.path.join(tmp, "sig.bin")
        with open(pub_path, "w", encoding="utf-8") as f:
            f.write(pub_pem.strip() + "\n")
        with open(msg_path, "wb") as f:
            f.write(message_bytes)
        with open(sig_path, "wb") as f:
            f.write(sig_bytes)

        proc = subprocess.run(
            [
                openssl_bin,
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                pub_path,
                "-rawin",
                "-in",
                msg_path,
                "-sigfile",
                sig_path,
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            raise ValueError(f"OpenSSL Ed25519 verification failed: {detail}")
        return "openssl-pkeyutl"


def extract_response_text(resp: Dict[str, Any]) -> str:
    choices = resp.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("Missing non-empty 'choices' array in response JSON")
    first = choices[0]
    if not isinstance(first, dict):
        raise ValueError("Invalid choices[0] entry")
    msg = first.get("message")
    if isinstance(msg, dict) and isinstance(msg.get("content"), str):
        return msg["content"]
    delta = first.get("delta")
    if isinstance(delta, dict) and isinstance(delta.get("content"), str):
        return delta["content"]
    raise ValueError("Missing string choices[0].message.content")


def verify_receipt(
    resp: Dict[str, Any],
    pinned_pub_pem: Optional[str] = None,
    response_text_override: Optional[str] = None,
    require_zdr: bool = False,
    require_zero_cost: bool = False,
) -> Dict[str, Any]:
    receipt = resp.get("veritas_receipt")
    if not isinstance(receipt, dict):
        raise ValueError("Missing 'veritas_receipt' object in response JSON")

    for req_field in ("signature", "public_key", "payload_sha256", "canonical_payload", "payload"):
        if req_field not in receipt or receipt[req_field] in (None, ""):
            raise ValueError(f"Missing required field veritas_receipt.{req_field}")

    canonical_payload = receipt["canonical_payload"]
    if not isinstance(canonical_payload, str):
        raise ValueError("veritas_receipt.canonical_payload must be a string")

    payload = receipt["payload"]
    if not isinstance(payload, dict):
        raise ValueError("veritas_receipt.payload must be an object")

    if json.loads(canonical_payload) != payload:
        raise ValueError("veritas_receipt.payload does not match canonical_payload JSON")

    computed_payload_sha = sha256_hex(canonical_payload.encode("utf-8"))
    if computed_payload_sha != str(receipt["payload_sha256"]):
        raise ValueError(
            f"payload_sha256 mismatch: expected {receipt['payload_sha256']}, got {computed_payload_sha}"
        )

    content_text = (
        response_text_override
        if response_text_override is not None
        else extract_response_text(resp)
    )
    computed_resp_sha = sha256_hex(content_text.encode("utf-8"))
    expected_resp_sha = str(payload.get("response_sha256") or "")
    if computed_resp_sha != expected_resp_sha:
        raise ValueError(
            f"response_sha256 mismatch: expected {expected_resp_sha}, got {computed_resp_sha}"
        )

    receipt_pub_pem = str(receipt["public_key"]).strip()
    if pinned_pub_pem:
        norm_pinned = pinned_pub_pem.strip()
        if norm_pinned != receipt_pub_pem:
            raise ValueError("Pinned public key does not match veritas_receipt.public_key")
        pub_to_use = norm_pinned
    else:
        pub_to_use = receipt_pub_pem

    backend = verify_ed25519_signature(
        pub_to_use,
        str(receipt["signature"]).strip(),
        canonical_payload.encode("utf-8"),
    )

    zdr_val = payload.get("zdr_enforced")
    cost_raw = payload.get("cost_usd")
    cost_val: Optional[float] = float(cost_raw) if cost_raw is not None else None

    if require_zdr and zdr_val is not True:
        raise ValueError(f"Receipt failed ZDR policy check: zdr_enforced={zdr_val!r}")
    if require_zero_cost and (cost_val is None or cost_val != 0.0):
        raise ValueError(f"Receipt failed zero-cost policy check: cost_usd={cost_raw!r}")

    # Strictly return non-proprietary attestation fields only (no models_used or pipeline_executed).
    return {
        "ok": True,
        "verdict": "ED25519_OFFLINE_VERIFIED",
        "crypto_backend": backend,
        "seq": receipt.get("seq"),
        "schema": payload.get("schema"),
        "model_requested": payload.get("model_requested"),
        "strict_free_only": payload.get("strict_free_only"),
        "cost_usd": cost_val if cost_raw is not None else None,
        "zdr_enforced": zdr_val,
        "payload_sha256": computed_payload_sha,
        "response_sha256": computed_resp_sha,
        "public_key_sha256": sha256_hex(pub_to_use.encode("utf-8")),
    }


def verify_jsonl_records(
    jsonl_path: str,
    pinned_pem: str,
    require_zdr: bool = False,
    require_zero_cost: bool = False,
) -> Dict[str, Any]:
    """Load and validate sanitized benchmark-captured receipt records offline."""
    records: List[Dict[str, Any]] = []
    verified_count = 0
    total_count = 0
    pinned_sha = sha256_hex(pinned_pem.strip().encode("utf-8"))

    with open(jsonl_path, "r", encoding="utf-8") as fh:
        for line_no, raw_line in enumerate(fh, 1):
            line = raw_line.strip()
            if not line:
                continue
            total_count += 1
            rec = json.loads(line)
            if isinstance(rec.get("veritas_receipt"), dict):
                res = verify_receipt(
                    rec,
                    pinned_pub_pem=pinned_pem,
                    require_zdr=require_zdr,
                    require_zero_cost=require_zero_cost,
                )
            else:
                if rec.get("ok") is not True or rec.get("verdict") != "ED25519_OFFLINE_VERIFIED":
                    raise ValueError(f"Pre-verified record failed on line {line_no}")
                if rec.get("public_key_sha256") != pinned_sha:
                    raise ValueError(f"Public key hash mismatch on line {line_no}")
                if require_zdr and rec.get("zdr_enforced") is not True:
                    raise ValueError(f"Captured receipt failed ZDR check on line {line_no}")
                if require_zero_cost and (rec.get("cost_usd") is None or float(rec["cost_usd"]) != 0.0):
                    raise ValueError(f"Captured receipt failed zero-cost check on line {line_no}")
                res = {
                    k: rec.get(k)
                    for k in (
                        "ok",
                        "verdict",
                        "crypto_backend",
                        "seq",
                        "schema",
                        "model_requested",
                        "strict_free_only",
                        "cost_usd",
                        "zdr_enforced",
                        "payload_sha256",
                        "response_sha256",
                        "public_key_sha256",
                    )
                }
            verified_count += 1
            records.append(res)

    return {
        "source": "live_benchmark_proxy_capture",
        "model_probed": records[0].get("model_requested") if records else None,
        "probe_count": total_count,
        "verified_count": verified_count,
        "pass_rate": round(verified_count / total_count, 4) if total_count > 0 else 0.0,
        "public_key_sha256": pinned_sha,
        "semantic_scope": (
            "Cryptographic non-repudiation of server-attested payload integrity over captured benchmark calls; "
            "not independent verification of remote RAM deletion or upstream billing."
        ),
        "receipts": records,
    }


def run_live_probes(
    base_url: str,
    api_key: str,
    model: str,
    count: int,
    pinned_pem: str,
    byt_api_key: str = "",
    byt_provider: str = "auto",
    require_zdr: bool = False,
    require_zero_cost: bool = False,
) -> Dict[str, Any]:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    records: List[Dict[str, Any]] = []
    verified_count = 0

    for idx in range(count):
        prompt = PROBE_PROMPTS[idx % len(PROBE_PROMPTS)]
        req_body = json.dumps(
            {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 512,
            }
        ).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if byt_api_key:
            headers["X-Big4-BYT-Provider-Key"] = byt_api_key
            if byt_provider and byt_provider != "auto":
                headers["X-Big4-BYT-Provider"] = byt_provider
        req = urllib.request.Request(
            endpoint,
            data=req_body,
            method="POST",
            headers=headers,
        )
        with urllib.request.urlopen(req, timeout=150) as resp:
            raw = resp.read().decode("utf-8")
        obj = json.loads(raw)
        ver = verify_receipt(
            obj,
            pinned_pub_pem=pinned_pem,
            require_zdr=require_zdr,
            require_zero_cost=require_zero_cost,
        )
        verified_count += 1
        records.append(ver)

    return {
        "source": "live_probes",
        "model_probed": model,
        "probe_count": count,
        "verified_count": verified_count,
        "pass_rate": 1.0 if count > 0 and verified_count == count else 0.0,
        "public_key_sha256": sha256_hex(pinned_pem.strip().encode("utf-8")),
        "semantic_scope": (
            "Cryptographic non-repudiation of server-attested payload integrity; "
            "not independent verification of remote RAM deletion or upstream billing."
        ),
        "receipts": records,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify offline Ed25519 cryptographic receipts")
    parser.add_argument("--response", default=None, help="Path to single OpenAI JSON response file, or '-' for stdin")
    parser.add_argument("--jsonl-in", default=None, help="Path to JSONL file of captured benchmark receipts")
    parser.add_argument("--public-key", required=True, help="Pinned Ed25519 SPKI PEM file path")
    parser.add_argument("--response-text", default=None, help="Optional explicit response text override")
    parser.add_argument("--live-probe-count", type=int, default=0, help="Run N live audit probes via BIG4_BASE_URL/BIG4_API_KEY")
    parser.add_argument("--model", default="big4-ciclo5-free", help="Model ID for live probe mode")
    parser.add_argument("--byt-api-key", default="", help="Optional ephemeral BYT provider API key")
    parser.add_argument("--byt-provider", default="auto", help="Optional BYT provider name")
    parser.add_argument("--require-zdr", action="store_true", help="Fail unless payload.zdr_enforced is True")
    parser.add_argument("--require-zero-cost", action="store_true", help="Fail unless payload.cost_usd == 0.0")
    parser.add_argument("--out", default=None, help="Optional path to write JSON audit report")
    args = parser.parse_args()

    pinned_pem = load_public_key_pem(args.public_key)

    if args.jsonl_in:
        report = verify_jsonl_records(
            args.jsonl_in,
            pinned_pem,
            require_zdr=args.require_zdr,
            require_zero_cost=args.require_zero_cost,
        )
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(rendered + "\n")
        print(rendered)
        return 0 if report["probe_count"] > 0 and report["verified_count"] == report["probe_count"] else 1

    if args.live_probe_count > 0:
        base_url = os.environ.get("BIG4_BASE_URL", "").strip()
        api_key = os.environ.get("BIG4_API_KEY", "").strip()
        byt_key = (args.byt_api_key or os.environ.get("BYT_API_KEY", "")).strip()
        byt_prov = (args.byt_provider or os.environ.get("BYT_PROVIDER", "auto")).strip()
        if not base_url or not api_key:
            print("Missing BIG4_BASE_URL or BIG4_API_KEY in environment", file=sys.stderr)
            return 2
        report = run_live_probes(
            base_url,
            api_key,
            args.model,
            args.live_probe_count,
            pinned_pem,
            byt_api_key=byt_key,
            byt_provider=byt_prov,
            require_zdr=args.require_zdr,
            require_zero_cost=args.require_zero_cost,
        )
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(rendered + "\n")
        print(rendered)
        return 0 if report["verified_count"] == report["probe_count"] else 1

    if args.response == "-":
        resp_obj = json.loads(sys.stdin.read())
    elif args.response:
        with open(args.response, "r", encoding="utf-8") as fh:
            resp_obj = json.loads(fh.read())
    else:
        print("Provide --response, --jsonl-in, or --live-probe-count", file=sys.stderr)
        return 2

    res = verify_receipt(
        resp_obj,
        pinned_pub_pem=pinned_pem,
        response_text_override=args.response_text,
        require_zdr=args.require_zdr,
        require_zero_cost=args.require_zero_cost,
    )
    rendered = json.dumps(res, indent=2, ensure_ascii=False)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(rendered + "\n")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
