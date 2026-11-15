#!/usr/bin/env python3
"""
Post-Evaluation Reporter for Official UK AI Safety Institute Inspect Logs.

Contains ZERO custom grading logic:
  - Reads native Inspect `.eval` logs written by `inspect eval`,
  - Extracts task-level and sanitized sample-level pass/fail outcomes,
  - Computes 95% Wilson confidence intervals and exact two-sided McNemar p-values,
  - Aggregates verified Ed25519 receipt fields dynamically (never hardcodes flags),
  - Strips all raw prompts, keys, and proprietary model/pipeline recipes,
  - Emits Markdown to $GITHUB_STEP_SUMMARY and verified JSON reports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

Z_95 = 1.959963984540054

FORBIDDEN_TRADE_SECRET_MARKERS = (
    "|byt:",
    '"models_used"',
    '"pipeline_executed"',
    '"hybrid_verified_solver"',
    '"consensus_type"',
)


def wilson_ci(k: int, n: int, z: float = Z_95) -> Dict[str, float]:
    if n <= 0:
        return {"low_pct": 0.0, "high_pct": 0.0}
    k_clamped = max(0, min(int(k), int(n)))
    p = k_clamped / n
    z2 = z * z
    denom = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denom
    half = (z * math.sqrt(max(0.0, (p * (1.0 - p) / n) + (z2 / (4.0 * n * n))))) / denom
    return {
        "low_pct": round(max(0.0, center - half) * 100.0, 2),
        "high_pct": round(min(1.0, center + half) * 100.0, 2),
    }


def mcnemar_exact(pairs: List[Tuple[bool, bool]]) -> Dict[str, Any]:
    n = len(pairs)
    n11 = n10 = n01 = n00 = 0
    for arm_a_ok, arm_b_ok in pairs:
        if arm_a_ok and arm_b_ok:
            n11 += 1
        elif (not arm_a_ok) and arm_b_ok:
            n10 += 1
        elif arm_a_ok and (not arm_b_ok):
            n01 += 1
        else:
            n00 += 1

    discordant = n10 + n01
    if discordant == 0:
        p_two = 1.0
        p_one = 1.0
    else:
        k_min = min(n10, n01)
        tail = sum(math.comb(discordant, i) for i in range(k_min + 1)) * (0.5 ** discordant)
        p_two = min(1.0, 2.0 * tail)
        p_one = min(1.0, sum(math.comb(discordant, i) for i in range(n10, discordant + 1)) * (0.5 ** discordant))

    arm_a_pct = (100.0 * (n11 + n01) / n) if n else 0.0
    arm_b_pct = (100.0 * (n11 + n10) / n) if n else 0.0
    return {
        "paired_items": n,
        "both_correct": n11,
        "arm_b_only_correct": n10,
        "arm_a_only_correct": n01,
        "both_wrong": n00,
        "discordant_pairs": discordant,
        "arm_a_pct": round(arm_a_pct, 2),
        "arm_b_pct": round(arm_b_pct, 2),
        "delta_pp": round(arm_b_pct - arm_a_pct, 2),
        "exact_two_sided_p": round(p_two, 6),
        "exact_one_sided_p_arm_b_gt_arm_a": round(p_one, 6),
    }


def _score_is_correct(score_obj: Any) -> Optional[bool]:
    if score_obj is None:
        return None
    val = getattr(score_obj, "value", score_obj)
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return float(val) >= 1.0
    if isinstance(val, str):
        norm = val.strip().upper()
        if norm in ("C", "CORRECT", "TRUE", "1", "PASS"):
            return True
        if norm in ("I", "INCORRECT", "FALSE", "0", "FAIL", "N", "NOANSWER"):
            return False
    return None


def _sha256_short(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def extract_task_and_samples(log_dir: str) -> tuple[List[Dict[str, Any]], Dict[tuple[str, str], Dict[str, Any]]]:
    rows: List[Dict[str, Any]] = []
    samples_map: Dict[tuple[str, str], Dict[str, Any]] = {}
    if not os.path.isdir(log_dir):
        return rows, samples_map

    from inspect_ai.log import list_eval_logs, read_eval_log

    log_infos = sorted(list_eval_logs(log_dir), key=lambda x: x.name)
    for info in log_infos:
        log = read_eval_log(info.name, header_only=False)
        task_name = str(log.eval.task or "unknown").split("/")[-1]
        status = str(log.status or "unknown")
        total = int((log.results.total_samples if log.results else 0) or 0)
        completed = int((log.results.completed_samples if log.results else 0) or 0)

        acc: Optional[float] = None
        stderr: Optional[float] = None
        scorer_name = ""
        if log.results and log.results.scores:
            first_score = log.results.scores[0]
            scorer_name = str(first_score.scorer or first_score.name or "")
            metrics = first_score.metrics or {}
            if "accuracy" in metrics:
                acc = float(metrics["accuracy"].value)
            elif metrics:
                first_metric = next(iter(metrics.values()))
                acc = float(first_metric.value)
            if "stderr" in metrics:
                stderr = float(metrics["stderr"].value)

        sample_correct_count = 0
        sample_seen_count = 0
        if getattr(log, "reductions", None):
            for red in log.reductions or []:
                for r_samp in getattr(red, "samples", None) or []:
                    sid = str(getattr(r_samp, "sample_id", ""))
                    ok_val = _score_is_correct(r_samp)
                    ans_text = str(getattr(r_samp, "answer", "") or "")
                    if ok_val is not None and sid:
                        sample_seen_count += 1
                        if ok_val:
                            sample_correct_count += 1
                        samples_map[(task_name, sid)] = {
                            "task": task_name,
                            "sample_id": sid,
                            "correct": ok_val,
                            "answer_sha256_prefix": _sha256_short(ans_text),
                        }
                break
        if sample_seen_count == 0 and getattr(log, "samples", None):
            for samp in log.samples or []:
                sid = str(getattr(samp, "id", ""))
                epoch = int(getattr(samp, "epoch", 1) or 1)
                key_sid = sid if epoch == 1 else f"{sid}#e{epoch}"
                ok_val: Optional[bool] = None
                ans_text = ""
                scores_dict = getattr(samp, "scores", None) or {}
                if isinstance(scores_dict, dict) and scores_dict:
                    first_sc = next(iter(scores_dict.values()))
                    ok_val = _score_is_correct(first_sc)
                    ans_text = str(getattr(first_sc, "answer", "") or "")
                if not ans_text and getattr(samp, "output", None):
                    ans_text = str(getattr(samp.output, "completion", "") or "")
                if ok_val is not None:
                    sample_seen_count += 1
                    if ok_val:
                        sample_correct_count += 1
                    samples_map[(task_name, key_sid)] = {
                        "task": task_name,
                        "sample_id": key_sid,
                        "correct": ok_val,
                        "answer_sha256_prefix": _sha256_short(ans_text),
                    }

        denom = total if total > 0 else max(completed, sample_seen_count)
        scored = sample_correct_count if sample_seen_count > 0 else (
            int(round(completed * acc)) if (acc is not None and completed > 0) else 0
        )
        honest_acc = (scored / denom) if denom > 0 else 0.0

        rows.append(
            {
                "task": task_name,
                "status": status,
                "scorer": scorer_name,
                "total_samples": total,
                "completed_samples": completed,
                "error_samples": max(0, total - completed),
                "correct": scored,
                "inspect_accuracy": acc,
                "honest_accuracy_over_total": round(honest_acc, 4),
                "wilson_95_ci_pct": wilson_ci(scored, denom),
                "stderr": stderr,
            }
        )
    return rows, samples_map


def check_no_secret_leak(payload_text: str) -> None:
    forbidden_literals: List[str] = list(FORBIDDEN_TRADE_SECRET_MARKERS)
    base_url = os.environ.get("BIG4_BASE_URL", "").strip()
    api_key = os.environ.get("BIG4_API_KEY", "").strip()
    byt_key = os.environ.get("BYT_API_KEY", "").strip()
    direct_key = os.environ.get("DIRECT_BASELINE_API_KEY", "").strip()
    if base_url:
        parsed_url = urllib.parse.urlparse(base_url)
        if parsed_url.password:
            forbidden_literals.append(parsed_url.password)
    for secret_val in (api_key, byt_key, direct_key):
        if secret_val and len(secret_val) >= 12:
            forbidden_literals.append(secret_val)
            forbidden_literals.append(secret_val[:12])
            forbidden_literals.append(secret_val[:16])

    for lit in forbidden_literals:
        if lit and lit in payload_text:
            raise RuntimeError(f"Secret or trade-secret marker detected in public output ({len(lit)} chars)")

    if re.search(
        r"(?:sk-big4-|sk-or-v1-|sk-ant-|gsk_|AIza[0-9A-Za-z_-]{10,}|ghp_[0-9A-Za-z]{20,}|github_pat_[0-9A-Za-z_]{20,})",
        payload_text,
    ):
        raise RuntimeError("Credential token prefix detected in sanitized public summary")

    if re.search(r"https?://[^/\s@]+:[^/\s@]+@", payload_text):
        raise RuntimeError("URL userinfo credential detected in sanitized public summary")

    allowed_hosts = (
        r"github\.com|ukgovernmentbeis\.github\.io|104-207-84-209\.sslip\.io|104\.207\.84\.209|"
        r"api\.big4\.cloud|openrouter\.ai|api\.openai\.com|api\.anthropic\.com|"
        r"generativelanguage\.googleapis\.com|api\.groq\.com|api\.deepseek\.com|"
        r"api\.x\.ai|api\.mistral\.ai|api\.cerebras\.ai|integrate\.api\.nvidia\.com"
    )
    if re.search(rf"https?://(?!{allowed_hosts})", payload_text, re.I):
        raise RuntimeError("Unexpected external URL detected in sanitized public summary")


def aggregate_receipt_attestations(ed_report: Dict[str, Any]) -> Dict[str, Any]:
    """Derive attestation summary dynamically from verified Ed25519 receipts only."""
    receipts = ed_report.get("receipts") or []
    verified_receipts = [r for r in receipts if isinstance(r, dict) and r.get("ok") is True]
    verified_count = len(verified_receipts)
    zdr_vals = [r.get("zdr_enforced") for r in verified_receipts if r.get("zdr_enforced") is not None]
    cost_vals: List[float] = []
    for r in verified_receipts:
        if r.get("cost_usd") is not None:
            try:
                cost_vals.append(float(r["cost_usd"]))
            except (TypeError, ValueError):
                pass

    vendor_attested_zdr_all_true: Optional[bool] = (
        (len(zdr_vals) == verified_count and all(z is True for z in zdr_vals))
        if verified_count > 0
        else None
    )
    vendor_attested_max_cost_usd: Optional[float] = (
        max(cost_vals)
        if (verified_count > 0 and len(cost_vals) == verified_count)
        else None
    )
    return {
        "source": ed_report.get("source"),
        "verified_count": int(ed_report.get("verified_count", verified_count) or 0),
        "probe_count": int(ed_report.get("probe_count", len(receipts)) or 0),
        "public_key_sha256": ed_report.get("public_key_sha256"),
        "vendor_attested_zdr_all_true": vendor_attested_zdr_all_true,
        "vendor_attested_max_cost_usd": vendor_attested_max_cost_usd,
        "cryptographic_scope": (
            "Ed25519 signatures verify payload integrity and signed non-repudiation of metadata "
            "declared by the signing server; they are not an independent audit of upstream billing or RAM erasure."
        ),
    }


def build_paired_samples_and_stats(
    arm_a_samples: Dict[tuple[str, str], Dict[str, Any]],
    arm_b_samples: Dict[tuple[str, str], Dict[str, Any]],
    tasks_order: List[str],
) -> tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Dict[str, Any]]]:
    all_keys = sorted(set(arm_a_samples.keys()) | set(arm_b_samples.keys()))
    sanitized_rows: List[Dict[str, Any]] = []
    by_task_pairs: Dict[str, List[Tuple[bool, bool]]] = {t: [] for t in tasks_order}
    overall_pairs: List[Tuple[bool, bool]] = []

    for key in all_keys:
        task, sid = key
        ra = arm_a_samples.get(key)
        rb = arm_b_samples.get(key)
        if ra is not None and rb is not None:
            pair = (bool(ra["correct"]), bool(rb["correct"]))
            overall_pairs.append(pair)
            by_task_pairs.setdefault(task, []).append(pair)
        sanitized_rows.append(
            {
                "task": task,
                "sample_id": sid,
                "arm_a_correct": ra["correct"] if ra is not None else None,
                "arm_b_correct": rb["correct"] if rb is not None else None,
                "arm_a_answer_sha256_prefix": ra["answer_sha256_prefix"] if ra is not None else None,
                "arm_b_answer_sha256_prefix": rb["answer_sha256_prefix"] if rb is not None else None,
            }
        )

    per_task_mcnemar = {
        t: mcnemar_exact(by_task_pairs.get(t, [])) for t in tasks_order if by_task_pairs.get(t)
    }
    overall_mcnemar = mcnemar_exact(overall_pairs) if overall_pairs else None
    return sanitized_rows, per_task_mcnemar, overall_mcnemar or {}


def main() -> int:
    parser = argparse.ArgumentParser(description="Render official UK AISI Inspect public audit summary")
    parser.add_argument("--arm-a-dir", "--naked-dir", dest="arm_a_dir", required=True)
    parser.add_argument("--arm-b-dir", "--big4-dir", dest="arm_b_dir", required=True)
    parser.add_argument("--arm-a-label", default="Direct Upstream Baseline")
    parser.add_argument("--arm-b-label", default="Big4 Cycle 5 ($0.00)")
    parser.add_argument("--arm-a-routing-mode", default="direct_upstream")
    parser.add_argument("--arm-a-independent", default="true")
    parser.add_argument("--audit-mode", default="free_zero_cost")
    parser.add_argument("--target-model", default="")
    parser.add_argument("--sample-seed", default="")
    parser.add_argument("--humaneval-sandbox", default="docker:docker/humaneval-compose.yaml (network_mode=none)")
    parser.add_argument("--ed25519", required=True)
    parser.add_argument("--vps-proof", default="", help="Optional JSON report produced by scripts/verify_vps_target.py")
    parser.add_argument("--samples-out", default="sanitized_sample_outcomes.json", help="Sanitized paired per-sample outcomes JSON")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    naked_rows, arm_a_samples = extract_task_and_samples(args.arm_a_dir)
    big4_rows, arm_b_samples = extract_task_and_samples(args.arm_b_dir)
    with open(args.ed25519, "r", encoding="utf-8") as fh:
        ed_report = json.load(fh)

    vps_proof: Optional[Dict[str, Any]] = None
    vps_proof_path = (args.vps_proof or "").strip()
    if vps_proof_path and os.path.isfile(vps_proof_path):
        with open(vps_proof_path, "r", encoding="utf-8") as fh:
            vps_proof = json.load(fh)

    by_task_naked = {r["task"]: r for r in naked_rows}
    by_task_big4 = {r["task"]: r for r in big4_rows}
    tasks_order = list(dict.fromkeys([r["task"] for r in naked_rows] + [r["task"] for r in big4_rows]))

    naked_total_correct = sum(r["correct"] for r in naked_rows)
    naked_total_items = sum(max(r["total_samples"], r["completed_samples"]) for r in naked_rows)
    big4_total_correct = sum(r["correct"] for r in big4_rows)
    big4_total_items = sum(max(r["total_samples"], r["completed_samples"]) for r in big4_rows)

    naked_pct = (100.0 * naked_total_correct / naked_total_items) if naked_total_items > 0 else 0.0
    big4_pct = (100.0 * big4_total_correct / big4_total_items) if big4_total_items > 0 else 0.0
    delta_pp = big4_pct - naked_pct

    sanitized_samples, per_task_mcnemar, overall_mcnemar = build_paired_samples_and_stats(
        arm_a_samples, arm_b_samples, tasks_order
    )
    ed_summary = aggregate_receipt_attestations(ed_report)
    arm_a_indep_bool = str(args.arm_a_independent).strip().lower() == "true"

    summary: Dict[str, Any] = {
        "schema_version": "2.1",
        "framework": "UK AI Safety Institute Inspect (inspect-ai + inspect-evals)",
        "non_affiliation_notice": (
            "Independent evaluation harness using the open-source Inspect library; "
            "neither endorsed by nor affiliated with the UK AI Safety Institute."
        ),
        "audit_mode": args.audit_mode,
        "target_model": args.target_model or None,
        "sample_seed": args.sample_seed or None,
        "humaneval_sandbox": args.humaneval_sandbox,
        "arm_a_label": args.arm_a_label,
        "arm_b_label": args.arm_b_label,
        "arm_a_independent_of_vendor_gateway": arm_a_indep_bool,
        "arm_a_routing_mode": args.arm_a_routing_mode,
        "tasks": [],
        "aggregate": {
            "arm_a_correct": naked_total_correct,
            "arm_a_total": naked_total_items,
            "arm_a_accuracy_pct": round(naked_pct, 2),
            "arm_a_wilson_95_ci_pct": wilson_ci(naked_total_correct, naked_total_items),
            "arm_b_correct": big4_total_correct,
            "arm_b_total": big4_total_items,
            "arm_b_accuracy_pct": round(big4_pct, 2),
            "arm_b_wilson_95_ci_pct": wilson_ci(big4_total_correct, big4_total_items),
            "delta_pp": round(delta_pp, 2),
            "paired_mcnemar": overall_mcnemar or None,
        },
        "ed25519_verification": ed_summary,
        "vps_target_verification": vps_proof,
    }

    target_banner = f" | Target Model: `{args.target_model}`" if args.target_model else ""
    seed_banner = f" | Seed: `{args.sample_seed}`" if args.sample_seed else ""
    lines = [
        f"## Paired Benchmark Evaluation Summary (v2.1) — Inspect (`{args.audit_mode}`{target_banner}{seed_banner})",
        "",
        f"- **Arm A Independence:** `{'DIRECT UPSTREAM PROVIDER (bypasses Big4 gateway)' if arm_a_indep_bool else 'VENDOR DEMO PASSTHROUGH (zero-key smoke mode)'}` (`{args.arm_a_routing_mode}`)",
        f"- **Code Sandbox:** `{args.humaneval_sandbox}` (credential-free container env)",
        "",
        f"| Benchmark | {args.arm_a_label} | {args.arm_b_label} | Delta (pp) | Paired McNemar p (2-sided) |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ]

    for t in tasks_order:
        rn = by_task_naked.get(t)
        rb = by_task_big4.get(t)
        pn = 100.0 * rn["honest_accuracy_over_total"] if rn else 0.0
        pb = 100.0 * rb["honest_accuracy_over_total"] if rb else 0.0
        dp = pb - pn
        n_str = f"{rn['correct']}/{max(rn['total_samples'], rn['completed_samples'])} ({pn:.1f}%)" if rn else "N/A"
        b_str = f"{rb['correct']}/{max(rb['total_samples'], rb['completed_samples'])} ({pb:.1f}%)" if rb else "N/A"
        mcn = per_task_mcnemar.get(t)
        p_str = f"`{mcn['exact_two_sided_p']:.4f}` (B+:{mcn['arm_b_only_correct']}/A+:{mcn['arm_a_only_correct']})" if mcn else "N/A"
        lines.append(f"| `{t}` | {n_str} | {b_str} | {dp:+.1f} pp | {p_str} |")
        summary["tasks"].append({"task": t, "arm_a": rn, "arm_b": rb, "delta_pp": round(dp, 2), "paired_mcnemar": mcn})

    agg_p_str = (
        f"`{overall_mcnemar['exact_two_sided_p']:.4f}` (B+:{overall_mcnemar['arm_b_only_correct']} / A+:{overall_mcnemar['arm_a_only_correct']})"
        if overall_mcnemar
        else "N/A"
    )
    a_ci = summary["aggregate"]["arm_a_wilson_95_ci_pct"]
    b_ci = summary["aggregate"]["arm_b_wilson_95_ci_pct"]

    vps_line = None
    if vps_proof:
        vps_ip = vps_proof.get("expected_vps_ip", "104.207.84.209")
        vps_port = vps_proof.get("target_port", 443)
        vps_host = vps_proof.get("target_hostname", "104-207-84-209.sslip.io")
        tls_ver = vps_proof.get("tls_version") or "TLS"
        avg_ms = vps_proof.get("tcp_tls_ping_avg_ms")
        avg_str = f"{avg_ms} ms" if avg_ms is not None else "N/A"
        vps_status = "VERIFIED" if vps_proof.get("verified") else "UNVERIFIED"
        vps_line = (
            f"- **Arm B Endpoint Routing Check:** `{vps_host}` resolved and connected over `{tls_ver}` "
            f"to `{vps_ip}:{vps_port}` (avg handshake `{avg_str}`, status `{vps_status}`)."
        )

    lines.extend(
        [
            (
                f"| **OVERALL AGGREGATE** | **{naked_total_correct}/{naked_total_items} ({naked_pct:.1f}%)** *(95% CI {a_ci['low_pct']:.1f}%–{a_ci['high_pct']:.1f}%)* | "
                f"**{big4_total_correct}/{big4_total_items} ({big4_pct:.1f}%)** *(95% CI {b_ci['low_pct']:.1f}%–{b_ci['high_pct']:.1f}%)* | "
                f"**{delta_pp:+.1f} pp** | {agg_p_str} |"
            ),
            "",
            (
                f"- **Ed25519 Payload Integrity & Non-Repudiation (`{ed_summary['source']}`):** "
                f"`{ed_summary['verified_count']}/{ed_summary['probe_count']}` verified against pinned key "
                f"(`public_key_sha256`: `{ed_summary['public_key_sha256']}`, "
                f"`vendor_attested_zdr_all_true={ed_summary['vendor_attested_zdr_all_true']}`, "
                f"`vendor_attested_max_cost_usd={ed_summary['vendor_attested_max_cost_usd']}`)."
            ),
            *( [vps_line] if vps_line else [] ),
            "- **Trade Secret & Credential Hygiene:** Proprietary Cycle 5 source code, prompts, internal model-mix metadata, and credentials are absent from all outputs.",
        ]
    )

    md_text = "\n".join(lines) + "\n"
    json_text = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    samples_payload = {
        "schema_version": "2.1",
        "audit_mode": args.audit_mode,
        "sample_seed": args.sample_seed or None,
        "paired_items_count": len(sanitized_samples),
        "overall_mcnemar": overall_mcnemar,
        "samples": sanitized_samples,
    }
    samples_text = json.dumps(samples_payload, indent=2, ensure_ascii=False) + "\n"

    check_no_secret_leak(md_text + "\n" + json_text + "\n" + samples_text)

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(json_text)
    if args.samples_out:
        with open(args.samples_out, "w", encoding="utf-8") as fh:
            fh.write(samples_text)

    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if step_summary_path:
        with open(step_summary_path, "a", encoding="utf-8") as fh:
            fh.write(md_text)

    print(md_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
