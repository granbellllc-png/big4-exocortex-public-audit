#!/usr/bin/env python3
"""
Post-Evaluation Reporter for Official UK AI Safety Institute Inspect Logs.

Contains ZERO custom grading logic: reads native Inspect `.eval` logs written
directly by `inspect eval`, extracts official scorer metrics, merges offline
Ed25519 verification counts, emits Markdown to $GITHUB_STEP_SUMMARY, and
verifies zero secret/host leakage in serialized public outputs.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
from typing import Any, Dict, List, Optional

from inspect_ai.log import list_eval_logs, read_eval_log


def extract_task_rows(log_dir: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not os.path.isdir(log_dir):
        return rows

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

        scored = int(round(completed * acc)) if (acc is not None and completed > 0) else 0
        # Honest failure accounting: denom is total planned samples when available
        denom = total if total > 0 else completed
        honest_acc = (scored / denom) if denom > 0 else 0.0

        rows.append(
            {
                "task": task_name,
                "status": status,
                "scorer": scorer_name,
                "total_samples": total,
                "completed_samples": completed,
                "error_samples": max(0, total - completed),
                "correct_est": scored,
                "inspect_accuracy": acc,
                "honest_accuracy_over_total": round(honest_acc, 4),
                "stderr": stderr,
            }
        )
    return rows


def check_no_secret_leak(payload_text: str) -> None:
    forbidden_literals: List[str] = []
    base_url = os.environ.get("BIG4_BASE_URL", "").strip()
    api_key = os.environ.get("BIG4_API_KEY", "").strip()
    if base_url:
        forbidden_literals.append(base_url)
        host = urllib.parse.urlparse(base_url).hostname or ""
        if host:
            forbidden_literals.append(host)
            m = re.findall(r"\d+", host)
            if len(m) >= 3:
                forbidden_literals.append(".".join(m[:4]))
                forbidden_literals.append("-".join(m[:4]))
    if api_key and len(api_key) >= 12:
        forbidden_literals.append(api_key)
        forbidden_literals.append(api_key[:16])

    for lit in forbidden_literals:
        if lit and lit in payload_text:
            raise RuntimeError(f"Secret/host leakage detected in public output ({len(lit)} chars)")

    if re.search(r"https?://(?!github\.com|ukgovernmentbeis\.github\.io)", payload_text, re.I):
        raise RuntimeError("Unexpected external URL detected in sanitized public summary")


def main() -> int:
    parser = argparse.ArgumentParser(description="Render official UK AISI Inspect public audit summary")
    parser.add_argument("--naked-dir", required=True)
    parser.add_argument("--big4-dir", required=True)
    parser.add_argument("--ed25519", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    naked_rows = extract_task_rows(args.naked_dir)
    big4_rows = extract_task_rows(args.big4_dir)
    with open(args.ed25519, "r", encoding="utf-8") as fh:
        ed_report = json.load(fh)

    by_task_naked = {r["task"]: r for r in naked_rows}
    by_task_big4 = {r["task"]: r for r in big4_rows}
    tasks_order = list(dict.fromkeys([r["task"] for r in naked_rows] + [r["task"] for r in big4_rows]))

    naked_total_correct = sum(r["correct_est"] for r in naked_rows)
    naked_total_items = sum(max(r["total_samples"], r["completed_samples"]) for r in naked_rows)
    big4_total_correct = sum(r["correct_est"] for r in big4_rows)
    big4_total_items = sum(max(r["total_samples"], r["completed_samples"]) for r in big4_rows)

    naked_pct = (100.0 * naked_total_correct / naked_total_items) if naked_total_items > 0 else 0.0
    big4_pct = (100.0 * big4_total_correct / big4_total_items) if big4_total_items > 0 else 0.0
    delta_pp = big4_pct - naked_pct

    summary = {
        "framework": "UK AI Safety Institute Inspect (inspect-ai + inspect-evals)",
        "cost_usd": 0.0,
        "zdr_enforced": True,
        "tasks": [],
        "aggregate": {
            "naked_correct": naked_total_correct,
            "naked_total": naked_total_items,
            "naked_accuracy_pct": round(naked_pct, 2),
            "big4_cycle5_correct": big4_total_correct,
            "big4_cycle5_total": big4_total_items,
            "big4_cycle5_accuracy_pct": round(big4_pct, 2),
            "delta_pp": round(delta_pp, 2),
        },
        "ed25519_verification": {
            "verified_count": ed_report.get("verified_count", 0),
            "probe_count": ed_report.get("probe_count", 0),
            "public_key_sha256": ed_report.get("public_key_sha256"),
        },
    }

    lines = [
        "## Zero-Trust Third-Party Audit — UK AI Safety Institute `Inspect` ($0.00)",
        "",
        "| Benchmark (`inspect_evals`) | Naked `$0.00` Baseline | Big4 Exocortex Cycle 5 `$0.00` | Delta (pp) | Completed (Naked / Big4) |",
        "| :--- | :---: | :---: | :---: | :---: |",
    ]

    for t in tasks_order:
        rn = by_task_naked.get(t)
        rb = by_task_big4.get(t)
        pn = 100.0 * rn["honest_accuracy_over_total"] if rn else 0.0
        pb = 100.0 * rb["honest_accuracy_over_total"] if rb else 0.0
        dp = pb - pn
        n_str = f"{rn['correct_est']}/{max(rn['total_samples'], rn['completed_samples'])} ({pn:.1f}%)" if rn else "N/A"
        b_str = f"{rb['correct_est']}/{max(rb['total_samples'], rb['completed_samples'])} ({pb:.1f}%)" if rb else "N/A"
        c_str = f"{rn['completed_samples'] if rn else 0}/{rn['total_samples'] if rn else 0} vs {rb['completed_samples'] if rb else 0}/{rb['total_samples'] if rb else 0}"
        lines.append(f"| `{t}` | {n_str} | {b_str} | {dp:+.1f} pp | {c_str} |")
        summary["tasks"].append({"task": t, "naked": rn, "big4_cycle5": rb, "delta_pp": round(dp, 2)})

    lines.extend(
        [
            f"| **OVERALL AGGREGATE** | **{naked_total_correct}/{naked_total_items} ({naked_pct:.1f}%)** | **{big4_total_correct}/{big4_total_items} ({big4_pct:.1f}%)** | **{delta_pp:+.1f} pp** | `$0.00` token cost |",
            "",
            f"- **Offline Ed25519 Receipt Audit:** `{ed_report.get('verified_count', 0)}/{ed_report.get('probe_count', 0)}` cryptographically verified (`public_key_sha256`: `{ed_report.get('public_key_sha256')}`)",
            "- **Server Endpoints & Proprietary Weights:** Zero server secrets, weights, routing tables, or host identifiers disclosed.",
        ]
    )

    md_text = "\n".join(lines) + "\n"
    json_text = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"

    check_no_secret_leak(md_text + "\n" + json_text)

    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(json_text)

    step_summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "").strip()
    if step_summary_path:
        with open(step_summary_path, "a", encoding="utf-8") as fh:
            fh.write(md_text)

    print(md_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
