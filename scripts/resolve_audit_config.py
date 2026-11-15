#!/usr/bin/env python3
"""
Deterministic Audit Configuration & Direct-Provider Routing Resolver.

Separates Arm A (Baseline) from Big4's gateway whenever an auditor supplies
an upstream provider token (`BYT_API_KEY` or `DIRECT_BASELINE_API_KEY`),
generates a CSPRNG shuffle seed by default, and masks sensitive credentials
for GitHub Actions logs.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
import urllib.parse
from typing import Any, Dict, Optional

DEFAULT_BIG4_BASE_URL = "https://104-207-84-209.sslip.io/v1"

PROVIDER_BASE_URLS: Dict[str, str] = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "groq": "https://api.groq.com/openai/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "xai": "https://api.x.ai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "cerebras": "https://api.cerebras.ai/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
}


def detect_provider(provider_override: str, api_key: str, target_model: str) -> str:
    """Resolve upstream provider name from explicit override, key prefix, or model format."""
    prov = (provider_override or "auto").strip().lower()
    if prov and prov != "auto":
        if prov not in PROVIDER_BASE_URLS:
            raise ValueError(f"Unsupported byt_provider '{prov}'")
        return prov

    key = (api_key or "").strip()
    if key.startswith("sk-or-"):
        return "openrouter"
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("AIza"):
        return "gemini"
    if key.startswith("gsk_"):
        return "groq"
    if key.startswith("xai-"):
        return "xai"
    if key.startswith("csk-"):
        return "cerebras"
    if key.startswith("nvapi-"):
        return "nvidia"
    if key.startswith("sk-proj-") or key.startswith("sk-"):
        if "/" in (target_model or ""):
            return "openrouter"
        return "openai"

    if "/" in (target_model or ""):
        return "openrouter"
    return "openrouter"


def resolve_seed(raw_seed: Optional[str]) -> int:
    """Return explicit non-negative seed or generate a fresh CSPRNG seed."""
    val = (raw_seed or "").strip().lower()
    if not val or val == "random":
        return secrets.randbelow(900_000_000) + 100_000_000
    parsed = int(val)
    if parsed < 0:
        raise ValueError("sample_seed must be non-negative or 'random'")
    return parsed


def validate_target_model(target_model: str) -> str:
    clean = (target_model or "").strip()
    if any(ch in clean for ch in ("|", "\n", "\r", ";", "`", "$")):
        raise ValueError("target_model contains forbidden control or delimiter characters.")
    return clean


def resolve_audit_config(
    *,
    audit_mode: str,
    target_model: str = "",
    byt_provider: str = "auto",
    sample_seed: str = "random",
    custom_holdout_jsonl: str = "",
    big4_base_url: str = DEFAULT_BIG4_BASE_URL,
    big4_api_key: str = "",
    byt_api_key: str = "",
    direct_baseline_api_key: str = "",
) -> Dict[str, Any]:
    """Compute non-secret execution config while decoupling Arm A whenever possible."""
    mode = (audit_mode or "free_zero_cost").strip()
    if mode not in (
        "free_zero_cost",
        "byt_model_boost",
        "free_big4_vs_direct_provider",
        "free_big4_vs_byt_naked",
    ):
        raise ValueError(f"Unsupported audit_mode '{mode}'")

    target = validate_target_model(target_model)
    clean_big4_url = (big4_base_url or "").strip() or DEFAULT_BIG4_BASE_URL
    key = (big4_api_key or "").strip()
    byt = (byt_api_key or "").strip()
    direct_key = (direct_baseline_api_key or "").strip() or byt
    seed_int = resolve_seed(sample_seed)
    holdout_path = (custom_holdout_jsonl or "").strip()

    if custom_holdout_jsonl:
        holdout_norm = os.path.normpath(holdout_path)
        if os.path.isabs(holdout_path) or holdout_norm.startswith("..") or ".." in holdout_path:
            raise ValueError("custom_holdout_jsonl must be a relative path inside the repository.")

    if not key:
        raise ValueError("BIG4_API_KEY must be configured.")

    if mode in ("byt_model_boost", "free_big4_vs_direct_provider", "free_big4_vs_byt_naked"):
        if not byt:
            raise ValueError(
                f"audit_mode='{mode}' requires BYT_API_KEY so Arm A can query the upstream provider directly."
            )
        if not target:
            raise ValueError(
                f"audit_mode='{mode}' requires an explicit target_model ID for direct upstream baseline comparison."
            )

    provider = detect_provider(byt_provider, direct_key or byt, target)
    upstream_url = PROVIDER_BASE_URLS[provider]

    if mode == "byt_model_boost":
        arm_a_independent = True
        arm_a_routing_mode = f"direct_upstream:{provider}"
        arm_a_model = target
        arm_a_inspect_model = f"openai-api/upstream/{target}"
        arm_a_label = f"Direct Upstream Baseline ({provider}:{target})"
        arm_a_byt = False

        arm_b_model = f"big4-ciclo5-byt:{target}"
        arm_b_inspect_model = f"openai-api/big4/{arm_b_model}"
        arm_b_label = f"Big4 Cycle 5 Orchestrated ({target})"
        arm_b_byt = True
        probe_model = arm_b_model
        probe_byt = True
    elif mode in ("free_big4_vs_direct_provider", "free_big4_vs_byt_naked"):
        arm_a_independent = True
        arm_a_routing_mode = f"direct_upstream:{provider}"
        arm_a_model = target
        arm_a_inspect_model = f"openai-api/upstream/{target}"
        arm_a_label = f"Direct Upstream Baseline ({provider}:{target})"
        arm_a_byt = False

        arm_b_model = "big4-ciclo5-free"
        arm_b_inspect_model = f"openai-api/big4/{arm_b_model}"
        arm_b_label = "Big4 Cycle 5 ($0.00)"
        # Crucially, BYT_API_KEY is NEVER transmitted to Big4 in direct comparison mode.
        arm_b_byt = False
        probe_model = "big4-ciclo5-free"
        probe_byt = False
    else:
        if direct_key and target:
            arm_a_independent = True
            arm_a_routing_mode = f"direct_upstream:{provider}"
            arm_a_model = target
            arm_a_inspect_model = f"openai-api/upstream/{target}"
            arm_a_label = f"Direct Upstream Free Baseline ({provider}:{target})"
            arm_a_byt = False
        else:
            suffix = f":{target}" if target else ""
            arm_a_independent = False
            arm_a_routing_mode = "vendor_passthrough_demo"
            arm_a_model = f"big4-base-free-nudo{suffix}"
            arm_a_inspect_model = f"openai-api/big4/{arm_a_model}"
            arm_a_label = f"Vendor Demo Baseline ({target or '$0.00'})"
            arm_a_byt = False

        arm_b_model = "big4-ciclo5-free"
        arm_b_inspect_model = f"openai-api/big4/{arm_b_model}"
        arm_b_label = "Big4 Cycle 5 ($0.00)"
        arm_b_byt = False
        probe_model = "big4-ciclo5-free"
        probe_byt = False

    return {
        "AUDIT_MODE": mode,
        "TARGET_MODEL": target,
        "BYT_PROVIDER": provider,
        "UPSTREAM_BASE_URL": upstream_url,
        "BIG4_BASE_URL_EFFECTIVE": clean_big4_url,
        "SAMPLE_SEED": str(seed_int),
        "CUSTOM_HOLDOUT_JSONL": holdout_path,
        "ARM_A_INDEPENDENT": "true" if arm_a_independent else "false",
        "ARM_A_ROUTING_MODE": arm_a_routing_mode,
        "ARM_A_MODEL": arm_a_model,
        "ARM_A_INSPECT_MODEL": arm_a_inspect_model,
        "ARM_A_LABEL": arm_a_label,
        "ARM_A_USES_BYT": "true" if arm_a_byt else "false",
        "ARM_B_MODEL": arm_b_model,
        "ARM_B_INSPECT_MODEL": arm_b_inspect_model,
        "ARM_B_LABEL": arm_b_label,
        "ARM_B_USES_BYT": "true" if arm_b_byt else "false",
        "PROBE_MODEL": probe_model,
        "PROBE_USES_BYT": "true" if probe_byt else "false",
    }


def emit_github_masks(
    big4_base_url: str,
    big4_api_key: str,
    byt_api_key: str,
    direct_baseline_api_key: str,
    provider: str,
    arm_b_uses_byt: bool = False,
) -> None:
    parsed_url = urllib.parse.urlparse(big4_base_url or "")
    if parsed_url.password:
        print(f"::add-mask::{parsed_url.password}")
    if big4_api_key:
        print(f"::add-mask::{big4_api_key}")
    for candidate in (byt_api_key, direct_baseline_api_key):
        val = (candidate or "").strip()
        if val:
            print(f"::add-mask::{val}")
    if arm_b_uses_byt and big4_api_key and byt_api_key:
        print(f"::add-mask::{big4_api_key}|byt:{provider}|{byt_api_key}")
        print(f"::add-mask::{big4_api_key}|byt:auto|{byt_api_key}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve audit routing and write GITHUB_ENV")
    parser.add_argument("--github-env", default=os.environ.get("GITHUB_ENV", ""))
    parser.add_argument("--emit-masks", action="store_true")
    args = parser.parse_args()

    big4_url = os.environ.get("BIG4_BASE_URL", "")
    big4_key = os.environ.get("BIG4_API_KEY", "")
    byt_key = os.environ.get("BYT_API_KEY", "")
    direct_key = os.environ.get("DIRECT_BASELINE_API_KEY", "")

    cfg = resolve_audit_config(
        audit_mode=os.environ.get("RAW_AUDIT_MODE", "free_zero_cost"),
        target_model=os.environ.get("RAW_TARGET_MODEL", ""),
        byt_provider=os.environ.get("RAW_BYT_PROVIDER", "auto"),
        sample_seed=os.environ.get("RAW_SAMPLE_SEED", "random"),
        custom_holdout_jsonl=os.environ.get("RAW_CUSTOM_HOLDOUT_JSONL", ""),
        big4_base_url=big4_url,
        big4_api_key=big4_key,
        byt_api_key=byt_key,
        direct_baseline_api_key=direct_key,
    )

    if args.emit_masks:
        emit_github_masks(
            big4_url,
            big4_key.strip(),
            byt_key.strip(),
            direct_key.strip(),
            cfg["BYT_PROVIDER"],
            arm_b_uses_byt=(cfg["ARM_B_USES_BYT"] == "true"),
        )

    if args.github_env:
        with open(args.github_env, "a", encoding="utf-8") as fh:
            for k, v in cfg.items():
                fh.write(f"{k}={v}\n")

    safe_summary = {
        k: v
        for k, v in cfg.items()
        if "KEY" not in k
    }
    print("Resolved audit configuration:", json.dumps(safe_summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
