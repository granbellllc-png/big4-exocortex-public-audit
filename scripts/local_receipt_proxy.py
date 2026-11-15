#!/usr/bin/env python3
"""
Localhost Client-Side Receipt-Capture Proxy for UK AISI Inspect Runs.

Runs on the auditor's / GitHub Actions runner (`127.0.0.1:18080`) between Inspect
and the remote audit endpoint:
  1. Forwards `/v1/*` requests verbatim over HTTPS to `--upstream-base-url`
     (ignoring client streaming flag if non-streaming is already used by Inspect,
     or passing through responses directly).
  2. For every non-streaming `/chat/completions` JSON response containing a
     `veritas_receipt`, verifies its Ed25519 signature immediately against
     `--public-key` and appends ONLY sanitized attestation metadata (no raw
     prompts, no API keys, no proprietary `models_used`/`pipeline_executed`) to
     `--receipt-log`.
  3. Strips `big4_ciclo5`, `veritas_receipt`, and `veritas` top-level metadata
     before returning standard OpenAI JSON to Inspect so `.eval` logs remain
     clean and zero-recipe.
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import socketserver
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from verify_ed25519_receipt import load_public_key_pem, verify_receipt


class _ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def strip_proprietary_fields(obj: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = dict(obj)
    for k in ("big4_ciclo5", "veritas_receipt", "veritas"):
        cleaned.pop(k, None)
    return cleaned


def validate_upstream_base_url(upstream_base: str) -> urllib.parse.ParseResult:
    parsed = urllib.parse.urlparse((upstream_base or "").strip())
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https" and host:
        return parsed
    if parsed.scheme == "http" and host in ("127.0.0.1", "localhost", "::1"):
        return parsed
    raise ValueError(
        f"Refusing non-HTTPS external upstream URL '{upstream_base}'. "
        "Only HTTPS remote endpoints or localhost HTTP test servers are permitted."
    )


def make_handler(
    upstream_base: str,
    pinned_pem: str,
    receipt_log_path: str,
    require_zdr: bool,
    require_zero_cost: bool,
):
    write_lock = threading.Lock()
    parsed_up = validate_upstream_base_url(upstream_base.rstrip("/"))
    up_prefix = parsed_up.path.rstrip("/")
    up_origin = f"{parsed_up.scheme}://{parsed_up.netloc}"

    class ProxyHandler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            # Never log HTTP headers or request details to stdout/stderr.
            return

        def _forward(self) -> None:
            length = int(self.headers.get("Content-Length") or "0")
            body_bytes = self.rfile.read(length) if length > 0 else None

            req_path = self.path
            if up_prefix and not req_path.startswith(up_prefix + "/") and req_path != up_prefix:
                # If client calls /v1/chat/completions when upstream already ends with /v1
                if up_prefix.endswith("/v1") and req_path.startswith("/v1"):
                    target_url = up_origin + req_path
                else:
                    target_url = upstream_base.rstrip("/") + req_path
            else:
                target_url = up_origin + req_path

            fwd_headers: Dict[str, str] = {}
            for hdr in ("Authorization", "Content-Type", "Accept", "X-Big4-BYT-Provider-Key", "X-Big4-BYT-Provider"):
                val = self.headers.get(hdr)
                if val:
                    fwd_headers[hdr] = val

            req = urllib.request.Request(
                target_url,
                data=body_bytes,
                method=self.command,
                headers=fwd_headers,
            )

            try:
                with urllib.request.urlopen(req, timeout=240) as resp:
                    raw = resp.read()
                    status = resp.status
                    ctype = resp.headers.get("Content-Type", "application/json")
            except urllib.error.HTTPError as exc:
                raw = exc.read()
                status = exc.code
                ctype = exc.headers.get("Content-Type", "application/json")
            except Exception as exc:
                raw = json.dumps({"error": {"message": f"Proxy upstream error: {type(exc).__name__}"}}).encode("utf-8")
                status = 502
                ctype = "application/json"

            if status == 200 and "application/json" in ctype.lower() and self.path.endswith("/chat/completions"):
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                    if isinstance(parsed, dict) and isinstance(parsed.get("veritas_receipt"), dict):
                        ver = verify_receipt(
                            parsed,
                            pinned_pub_pem=pinned_pem,
                            require_zdr=require_zdr,
                            require_zero_cost=require_zero_cost,
                        )
                        with write_lock:
                            os.makedirs(os.path.dirname(os.path.abspath(receipt_log_path)), exist_ok=True)
                            with open(receipt_log_path, "a", encoding="utf-8") as fh:
                                fh.write(json.dumps(ver, ensure_ascii=False) + "\n")
                    cleaned = strip_proprietary_fields(parsed) if isinstance(parsed, dict) else parsed
                    raw = json.dumps(cleaned, ensure_ascii=False).encode("utf-8")
                except Exception as exc:
                    err_payload = json.dumps(
                        {"error": {"message": f"Receipt verification failure: {type(exc).__name__}: {exc}"}}
                    ).encode("utf-8")
                    self.send_response(502)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(err_payload)))
                    self.end_headers()
                    self.wfile.write(err_payload)
                    return

            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            if raw:
                self.wfile.write(raw)

        def do_GET(self) -> None:
            if self.path == "/health":
                ok_bytes = b'{"status":"ok","proxy":"local_receipt_proxy"}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(ok_bytes)))
                self.end_headers()
                self.wfile.write(ok_bytes)
                return
            self._forward()

        def do_POST(self) -> None:
            self._forward()

    return ProxyHandler


def main() -> int:
    parser = argparse.ArgumentParser(description="Local receipt-verifying reverse proxy for Inspect Arm B")
    parser.add_argument("--listen-host", default="127.0.0.1")
    parser.add_argument("--listen-port", type=int, default=18080)
    parser.add_argument("--upstream-base-url", required=True)
    parser.add_argument("--public-key", required=True)
    parser.add_argument("--receipt-log", required=True)
    parser.add_argument("--require-zdr", action="store_true")
    parser.add_argument("--require-zero-cost", action="store_true")
    args = parser.parse_args()

    pinned_pem = load_public_key_pem(args.public_key)
    handler = make_handler(
        args.upstream_base_url,
        pinned_pem,
        args.receipt_log,
        args.require_zdr,
        args.require_zero_cost,
    )
    server = _ThreadingHTTPServer((args.listen_host, args.listen_port), handler)
    print(f"Receipt proxy listening on http://{args.listen_host}:{args.listen_port}/v1", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
