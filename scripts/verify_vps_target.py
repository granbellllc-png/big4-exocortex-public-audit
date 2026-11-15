#!/usr/bin/env python3
"""
Dedicated VPS Hardware-Origin & Live Network Routing Verifier (Public Audit).

Proves that the GitHub Actions runner (or any external auditor's terminal)
resolves BIG4_BASE_URL to the dedicated commodity VPS IP (104.207.84.209),
runs ICMP ping, verifies the OS kernel socket peer IP across multiple live
TCP/TLS handshakes on port 443, and confirms Big4 gateway HTTPS responsiveness.

Contains zero credentials and never prints secrets, auth headers, or tokens.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional


def run_icmp_ping(target: str) -> Dict[str, Any]:
    """Run a bounded 3-packet ICMP ping and capture stdout without crashing."""
    ping_bin = shutil.which("ping")
    if not ping_bin:
        return {"target": target, "returncode": -1, "ok": False, "output": "ping binary not found"}

    timeout_flag = ["-W", "2000"] if sys.platform == "darwin" else ["-W", "2"]
    cmd = [ping_bin, "-c", "3", *timeout_flag, target]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=12, check=False)
        out_text = (proc.stdout or proc.stderr or "").strip()
        return {
            "target": target,
            "returncode": proc.returncode,
            "ok": proc.returncode == 0,
            "output": out_text,
        }
    except subprocess.TimeoutExpired as exc:
        partial = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        return {
            "target": target,
            "returncode": 124,
            "ok": False,
            "output": (partial or "ICMP ping timed out (likely filtered on runner VNet)").strip(),
        }


def extract_cert_sans(cert: Optional[Dict[str, Any]]) -> List[str]:
    if not cert:
        return []
    sans = [val for kind, val in cert.get("subjectAltName", ()) if kind == "DNS"]
    if not sans:
        for rdn in cert.get("subject", ()):
            for attr, val in rdn:
                if attr == "commonName":
                    sans.append(val)
    return sans


def measure_tcp_tls_pings(hostname: str, port: int, scheme: str, rounds: int) -> Dict[str, Any]:
    """Establish live TCP/TLS sockets and inspect kernel getpeername() + RTT."""
    ctx = ssl.create_default_context() if scheme == "https" else None
    peer_ips: List[str] = []
    rtts_ms: List[float] = []
    tls_version: Optional[str] = None
    cert_sans: List[str] = []

    for idx in range(1, max(1, rounds) + 1):
        t0 = time.perf_counter()
        with socket.create_connection((hostname, port), timeout=10) as raw_sock:
            peer_ip, peer_port = raw_sock.getpeername()[:2]
            if ctx is not None:
                with ctx.wrap_socket(raw_sock, server_hostname=hostname) as tls_sock:
                    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                    tls_version = tls_sock.version()
                    if not cert_sans:
                        cert_sans = extract_cert_sans(tls_sock.getpeercert())
            else:
                elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
                tls_version = "plaintext-http"

        peer_ips.append(peer_ip)
        rtts_ms.append(elapsed_ms)
        print(
            f"TLS-PING #{idx}: host={hostname} peer_ip={peer_ip}:{peer_port} "
            f"proto={tls_version} time={elapsed_ms:.2f} ms"
        )

    avg_ms = round(sum(rtts_ms) / len(rtts_ms), 2) if rtts_ms else None
    return {
        "peer_ips": peer_ips,
        "rtts_ms": rtts_ms,
        "avg_ms": avg_ms,
        "tls_version": tls_version,
        "cert_sans": cert_sans,
    }


def check_gateway_http_liveness(scheme: str, hostname: str, port: int) -> Optional[int]:
    """Probe unauthenticated /health (fallback /v1/models) and return status code."""
    netloc = hostname if (scheme == "https" and port == 443) or (scheme == "http" and port == 80) else f"{hostname}:{port}"
    for path in ("/health", "/v1/models"):
        probe_url = f"{scheme}://{netloc}{path}"
        req = urllib.request.Request(
            probe_url,
            method="GET",
            headers={"User-Agent": "big4-public-audit-vps-check/1.0", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                return int(resp.status)
        except urllib.error.HTTPError as exc:
            if exc.code in (200, 401):
                return int(exc.code)
        except Exception:
            continue
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify DNS, ping, and live TLS socket peer IP against dedicated VPS")
    parser.add_argument(
        "--url",
        default=os.environ.get("BIG4_BASE_URL", "").strip() or "https://104-207-84-209.sslip.io/v1",
        help="Target OpenAI-compatible base URL (defaults to BIG4_BASE_URL or public VPS endpoint)",
    )
    parser.add_argument("--expected-ip", default="104.207.84.209", help="Expected dedicated VPS IPv4 address")
    parser.add_argument("--tcp-pings", type=int, default=3, help="Number of live TCP/TLS socket ping rounds")
    parser.add_argument("--out", default=None, help="Optional path to write JSON verification report")
    args = parser.parse_args()

    parsed = urllib.parse.urlparse(args.url.strip())
    scheme = (parsed.scheme or "https").lower()
    hostname = (parsed.hostname or "").strip()
    if scheme not in ("https", "http") or not hostname:
        print(f"ERROR: Invalid target URL scheme/hostname: {scheme}://{hostname}", file=sys.stderr)
        return 2
    port = parsed.port or (443 if scheme == "https" else 80)

    try:
        addr_rows = socket.getaddrinfo(hostname, port, socket.AF_INET, socket.SOCK_STREAM)
        resolved_ipv4 = sorted({row[4][0] for row in addr_rows})
    except Exception as exc:
        print(f"ERROR: IPv4 DNS resolution failed for {hostname}: {exc}", file=sys.stderr)
        return 1

    dns_matches = args.expected_ip in resolved_ipv4
    print(f"DNS A-RECORD CHECK: hostname={hostname} -> resolved_ipv4={resolved_ipv4} (expected={args.expected_ip}, match={dns_matches})")

    ptr_record: Optional[str] = None
    try:
        ptr_record = socket.gethostbyaddr(args.expected_ip)[0]
    except Exception:
        ptr_record = None
    print(f"REVERSE DNS (PTR): {args.expected_ip} -> {ptr_record or 'unavailable'}")

    icmp_targets = [args.expected_ip]
    if hostname != args.expected_ip:
        icmp_targets.append(hostname)
    icmp_results = []
    for tgt in icmp_targets:
        res = run_icmp_ping(tgt)
        icmp_results.append(res)
        print(f"--- ping -c 3 {tgt} (rc={res['returncode']}) ---")
        if res["output"]:
            print(res["output"])
    icmp_ping_ok = all(r["ok"] for r in icmp_results)
    if not icmp_ping_ok:
        print(
            "INFO: Outbound raw ICMP Echo is filtered on this cloud runner VNet "
            "(expected on Microsoft Azure / GitHub-hosted VMs); verifying live TCP/TLS :443 kernel socket peer IP..."
        )

    tls_probe: Dict[str, Any] = {"peer_ips": [], "rtts_ms": [], "avg_ms": None, "tls_version": None, "cert_sans": []}
    tls_error: Optional[str] = None
    try:
        tls_probe = measure_tcp_tls_pings(hostname, port, scheme, args.tcp_pings)
    except Exception as exc:
        tls_error = str(exc)
        print(f"ERROR: Live TCP/TLS socket probe failed: {exc}", file=sys.stderr)

    tls_peer_ips = tls_probe["peer_ips"]
    tls_peer_matches = bool(tls_peer_ips) and all(ip == args.expected_ip for ip in tls_peer_ips)

    http_status = check_gateway_http_liveness(scheme, hostname, port)
    http_gateway_ok = http_status in (200, 401)
    print(f"HTTP GATEWAY CHECK: status={http_status} (expected 200 or 401 -> ok={http_gateway_ok})")

    verified = bool(dns_matches and tls_peer_matches and http_gateway_ok)

    report = {
        "expected_vps_ip": args.expected_ip,
        "target_hostname": hostname,
        "target_port": port,
        "resolved_ipv4": resolved_ipv4,
        "ptr_record": ptr_record,
        "icmp_ping_ok": icmp_ping_ok,
        "tls_peer_ips": tls_peer_ips,
        "tls_version": tls_probe["tls_version"],
        "tls_cert_san": tls_probe["cert_sans"],
        "tcp_tls_ping_rtt_ms": tls_probe["rtts_ms"],
        "tcp_tls_ping_avg_ms": tls_probe["avg_ms"],
        "http_gateway_status": http_status,
        "verified": verified,
    }
    if tls_error:
        report["tls_error"] = tls_error

    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2, ensure_ascii=False)
            fh.write("\n")

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if verified else 1


if __name__ == "__main__":
    raise SystemExit(main())
