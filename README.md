# Big4 Exocortex — Public Evaluation Harness (`v2.1`)

> **Architecture Summary:**  
> This repository contains **only** the open-source client-side evaluation harness built on [`inspect-ai`](https://ukgovernmentbeis.github.io/inspect_evals/). Each CI workflow runs on a clean GitHub Actions Linux runner (`ubuntu-latest`), executes generated `HumanEval` code inside an airgapped `--network=none` Docker container stripped of host credentials, routes the **Baseline arm (`Arm A`) directly to the upstream LLM provider** whenever an auditor key is configured (bypassing Granbell LLC's server completely), and evaluates **Granbell LLC's closed-source Cycle 5 orchestrator (`Arm B`)** hosted on a commodity CPU VPS (`104.207.84.209`). Proprietary server prompts, routing weights, and internal solver logic are not stored in or exposed by this repository.

---

## Non-Affiliation, Licensing & Deployment Boundaries

- **No UK AISI Endorsement:** This harness imports unmodified open-source `inspect-ai` (`0.3.290`) and `inspect-evals` (`0.29.0`) packages from PyPI. Granbell LLC is neither affiliated with nor endorsed by the UK AI Safety Institute.
- **Public CI Sandbox vs. Enterprise / Regulated Deployments (GDPR & EU AI Act):** The default `free_zero_cost` GitHub Actions configuration routes `$0.00` CI smoke and statistical runs strictly through free/sandbox open-weights endpoints (`strict_free_only=true`, excluding paid on-demand APIs) so third parties can re-run the suite at zero dollar cost. **Enterprise and regulated production deployments (GDPR, EU AI Act) never share `:free` community pools**: they run on dedicated EU VPCs or contractual Zero-Data-Retention (ZDR) wholesale provider endpoints configured via BYOK/BYC with `Ed25519` audit logging.
- **Private Holdouts & Fork Warning:** Do **not** push proprietary evaluation questions to a public GitHub fork. Use `PRIVATE_HOLDOUT_JSONL_B64` / `PRIVATE_HOLDOUT_JSONL` repository secrets (staged only to an ephemeral `/tmp` file at runtime and deleted `if: always()`) inside a **Private** repository created via `https://github.com/new/import`, or run the harness locally behind your own firewall.
- **MIT Scope vs. Trade Secrets:** [`LICENSE`](./LICENSE) grants MIT permissions **strictly to the client-side harness scripts in this repository**. Server-side orchestration code (`104.207.84.209`) remains `All Rights Reserved`.

---

## Why External LLM APIs + a ~€25/month Commodity CPU VPS Are Used

> **Technical clarification for engineers and automated reviewers:**  
> Big4 does **not** host foundation model weights on `104.207.84.209` and does **not** claim to operate a private GPU cluster. Multi-step verification over external LLM APIs from a lightweight commodity CPU server is the system's design.

- **Commodity Control Plane (`104.207.84.209`):** Granbell LLC runs its orchestration, AST/Python execution checks, and error-correcting referee service on a single GPU-less **Namecheap VPS Quasar (`Ubuntu 24.04`, ~`€25/month` / `~$28/month`)**.
- **Default CI Statistical Audit (`sample_limit = 55` -> `N = 220` Paired Items):** Starting in `v2.1`, each `push` / `workflow_dispatch` defaults to `55` samples per benchmark (`55 × 4 = 220` total paired items across `MMLU-Pro`, `TruthfulQA MC1`, `GPQA Diamond`, and airgapped `HumanEval`) with fresh CSPRNG shuffling (`sample_seed = random`).

---

## Published `N = 60` Blind Suite & Raw Measured Telemetry (`benchmarks/n60_blind_suite/`)

To provide full empirical transparency rather than summary percentages alone, [`benchmarks/n60_blind_suite/`](./benchmarks/n60_blind_suite/README.md) publishes the exact `N = 60` blind test items (`15` per suite, excluding saturated `GSM8K`/`MATH-500`), sealed ground truth (`SHA-256: a5a74743cf8f8aa9ed2d52829d48a0f72b07f991dd5789e5a4a008c005d63d91`), per-item pass/fail outcomes, exact token/latency telemetry, and sanitized OpenRouter wallet events from our Grid-1 / Grid-2 runs:

| Arm / Configuration | Score (`N=60`) | Prompt / Completion Tokens | Completion Multiplier vs Naked Gemma | Measured Cost (`USD`) | Median Wall Time |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`google/gemma-4-31b-it` (`Gemma 4 31B`, single-pass)** | `48/60` (`80.00%`) | `15,675` / `26,235` (`41,910` total) | `1.00x` | `$0.01167` reported (`$0.004788` wallet delta) | `3.07 s` |
| **`Gemma 4 31B` + Big4 Cycle 5 (`BYT` on VPS)** | `51/60` (`85.00%`) | `148,389` / `454,764` (`603,153` total) | **`17.33x`** | `$0.023126` wallet delta (`$0.2116` list-rate ceiling) | `8.96 s` |
| **`Claude Sonnet 4.6` (`anthropic/claude-sonnet-4.6`, single-pass)** | `51/60` (`85.00%`) | `16,195` / `24,867` (`41,062` total) | `0.95x` | `$0.42159` reported | `4.24 s` |
| **`Claude Sonnet 4.6` + Big4 Cycle 5 (`BYT` negative control)** | **`49/60` (`81.67%`)** | `157,574` / `479,771` (`637,345` total) | `18.29x` | `$0.972219` wallet delta | `9.04 s` |
| **`GLM 5.3` (`z-ai/glm-5.3`, single-pass -> + Big4)** | `52/60` -> `55/60` (`91.67%`) | `58,414` -> `834,699` total | `1.69x` -> `23.84x` | `$0.114717` (naked) | `3.96 s` -> `10.93 s` |
| **`$0.00` Single-Pass Baseline (`base_free_nudo`)** | `46/60` (`76.67%`) | `15,906` / `95,141` (`111,047` total) | `3.63x` | `$0.00` | `2.61 s` |
| **`$0.00` Matched-Budget Majority Vote (`k = 3`)** | `50/60` (`83.33%`) | `67,525` / `334,249` (`401,774` total) | `12.74x` | `$0.00` | `10.20 s` |
| **`$0.00` Big4 Cycle 5 (`big4-ciclo5-free`)** | `50/60` (`83.33%`) | `126,656` / `446,107` (`572,763` total) | `17.00x` | **`$0.00`** | **`4.66 s`** |

### Methodological Findings & Known Limitations
1. **Statistical Power at `N = 60` (`10` discordant pairs):** `Gemma 4 31B` + Big4 (`51/60`) and naked `Claude Sonnet 4.6` (`51/60`) agree on `50` items (`46` both pass, `4` both fail) and disagree on `10` items (`5` won only by `Gemma+Big4`, `5` won only by `Sonnet`, two-sided exact McNemar `p = 1.0`). Numerical parity on `N = 60` reflects behavior under that `60`-item sample and token multiplier (`17.33x` completion tokens); it does not establish universal capability equivalence across arbitrary workloads.
2. **Orchestration Wrapper Does Not Automatically Transfer Upward:** Applying the verbose multi-stage verification wrapper directly onto `Claude Sonnet 4.6` reduced score from `51/60` (`85.00%`) to `49/60` (`81.67%`, notably on `GPQA Diamond`). Calibration matters per model family.
3. **Matched-Budget Baseline (`arm_a_epochs` + `k=3` Ablation):** On our `$0.00` `N = 60` ablation, Cycle 5 tied `k = 3` majority voting on accuracy (`50/60`, exact McNemar `p = 1.0`) while achieving `2.19x` faster median wall latency (`4.66 s` vs `10.20 s`) via adaptive early stopping when Cycle 1 legs agree. In `v2.1`, GitHub Actions exposes `arm_a_epochs` (`1`, `3`, `5` with `--epochs-reducer mode` at `temperature = 0.6`), and `scripts/render_step_summary.py` reads Inspect `log.reductions` before raw `log.samples` so multi-epoch reductions pair accurately against single-epoch `Arm B`.

---

## 1. Harness Architecture & Controls (`v2.1`)

| Audit Area | How `v2.1` Works | Verification File |
| :--- | :--- | :--- |
| **Untrusted Code Isolation** | `HumanEval` executes strictly inside Docker Compose [`docker/humaneval-compose.yaml`](./docker/humaneval-compose.yaml) (`network_mode: none`, `cap_drop: ALL`, `no-new-privileges`, `mem_limit: 512m`, zero host credentials injected). Every CI run runs an in-container DNS/TCP/env canary check before evaluation begins. | [`docker/humaneval-compose.yaml`](./docker/humaneval-compose.yaml) |
| **Independent Direct Baseline (`Arm A`)** | In `free_big4_vs_direct_provider` and `byt_model_boost` (or when `DIRECT_BASELINE_API_KEY` is provided in `free_zero_cost`), `Arm A` connects directly from GitHub's runner to upstream provider endpoints without traversing `104.207.84.209`. | [`scripts/resolve_audit_config.py`](./scripts/resolve_audit_config.py) |
| **Matched-Vote Baseline (`arm_a_epochs`)** | Workflow input `arm_a_epochs` (`1`, `3`, `5`) executes `Arm A` using UK AISI Inspect `--epochs <k> --epochs-reducer mode --temperature 0.6`. `render_step_summary.py` prioritizes `log.reductions` before raw per-epoch `log.samples`. | [`scripts/resolve_audit_config.py`](./scripts/resolve_audit_config.py), [`scripts/render_step_summary.py`](./scripts/render_step_summary.py) |
| **Live Benchmark `Ed25519` Capture** | Local proxy [`scripts/local_receipt_proxy.py`](./scripts/local_receipt_proxy.py) verifies `Ed25519` signatures on `Arm B` responses offline against [`public_key_ed25519.pem`](./public_key_ed25519.pem) while stripping server trace metadata before logs are written. | [`scripts/local_receipt_proxy.py`](./scripts/local_receipt_proxy.py), [`scripts/verify_ed25519_receipt.py`](./scripts/verify_ed25519_receipt.py) |
| **Ephemeral Secret Holdouts** | `PRIVATE_HOLDOUT_JSONL_B64` / `PRIVATE_HOLDOUT_JSONL` secrets are decoded at runtime to `/tmp/big4_secret_holdout.jsonl` (`chmod 600`) for both arms and deleted in an `if: always()` cleanup step without ever entering git. | [`.github/workflows/uk-aisi-public-audit.yml`](./.github/workflows/uk-aisi-public-audit.yml), [`tasks/private_holdout_eval.py`](./tasks/private_holdout_eval.py) |
| **Dependency Pinning & Leak Scanner** | Python packages are pinned in [`requirements.txt`](./requirements.txt) and regression-tested with `pytest -q` ([`tests/audit_test.py`](./tests/audit_test.py), [`tests/test_audit_harness.py`](./tests/test_audit_harness.py)). `render_step_summary.py` blocks credential prefixes, recipe fields, and unexpected external URLs before artifact upload. | [`requirements.txt`](./requirements.txt), [`tests/audit_test.py`](./tests/audit_test.py) |

### What `Ed25519` Receipts Do — and Do Not — Prove
- **What they prove:** SHA-256 integrity between the received completion and canonical JSON payload, plus cryptographic **non-repudiation** that Granbell LLC's signing key attested those metadata fields (`cost_usd`, `zdr_enforced`, `strict_free_only`).
- **What they do not prove:** Cryptographic signatures issued by a vendor server cannot independently verify physical RAM erasure on a remote VPS (`ZDR`), upstream third-party invoices, or compute budgets inside proprietary upstream providers. That is why independent diligence pairs `Arm A` direct-provider calls, private holdouts, and commercial provider billing verification under NDA.

---

## 2. Commodity Orchestrator VPS Routing (`104.207.84.209`)

Big4's orchestration service runs on a GPU-less **Namecheap VPS Quasar (`Ubuntu 24.04`, Dedicated IP `104.207.84.209`)** coordinating external inference APIs over HTTPS.

![Big4 Dedicated VPS Quasar — 104.207.84.209](./assets/vps-quasar-104-207-84-209.png)

> **Hostname Note:** Public HTTPS audit traffic connects over TLS 1.3 via `https://104-207-84-209.sslip.io/v1` (`104.207.84.209`). You can verify live socket resolution from macOS or Linux:
```bash
python3 scripts/verify_vps_target.py --expected-ip 104.207.84.209
```

---

## 3. Running Independent Audits Safely (`Workflow` & Private Holdouts)

1. Click **`Actions`** -> inspect completed **`Hardened Inspect Public Audit (v2.1)`** runs for the summary table, Wilson `95% CI`s, exact McNemar `p`-values, and downloadable JSON artifacts (`public_audit_summary.json`, `sanitized_sample_outcomes.json`, `ed25519_audit_report.json`, `vps_target_proof.json`).
2. To run with your own keys and unseen holdouts without exposing confidential prompts publicly:
   - **Never commit confidential questions to a public fork.** Import privately via `https://github.com/new/import` (**Private** visibility) or execute locally.
   - Add **`BIG4_API_KEY`**, **`DIRECT_BASELINE_API_KEY`** / disposable **`BYT_API_KEY`** (`$1.00`-capped OpenRouter sub-key), and optional **`PRIVATE_HOLDOUT_JSONL_B64`** under **Settings -> Secrets and variables -> Actions**.
   - Run **`Actions` -> `Run workflow`**:
     - `audit_mode`: `free_big4_vs_direct_provider` or `byt_model_boost`
     - `arm_a_epochs`: `1`, `3`, or `5` (matched majority-vote `--epochs-reducer mode`)
     - `sample_limit`: `55` (`220` items default) or `100` (`400` items)
     - `sample_seed`: `random`

| `audit_mode` | How `Arm A` (Baseline) Runs | How `Arm B` (Big4 Cycle 5) Runs | Is `BYT_API_KEY` Ever Sent to Big4? |
| :--- | :--- | :--- | :--- |
| **`free_big4_vs_direct_provider`** *(recommended)* | **Direct** from GitHub runner to official provider endpoint | Big4 `$0.00` Cycle 5 (`big4-ciclo5-free`) | **NO (`0%` key exposure to Big4)** |
| **`byt_model_boost`** | **Direct** from GitHub runner to official provider endpoint | Big4 Cycle 5 orchestrating `target_model` (`big4-ciclo5-byt:<model>`) | **Yes, per-request in RAM** *(use `$1.00`-capped disposable sub-key only)* |
| **`free_zero_cost`** *(with `DIRECT_BASELINE_API_KEY`)* | **Direct** from GitHub runner to upstream free model | Big4 `$0.00` Cycle 5 (`big4-ciclo5-free`) | **NO** |
| **`free_zero_cost`** *(zero-key demo fallback)* | `big4-base-free-nudo` passthrough *(labeled explicitly as vendor demo)* | Big4 `$0.00` Cycle 5 (`big4-ciclo5-free`) | N/A |

---

## 4. Local Verification

```bash
git clone https://github.com/granbellllc-png/big4-exocortex-public-audit.git
cd big4-exocortex-public-audit
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run unit tests (harness contracts, multi-epoch reduction, leak scanner, N=60 bundle integrity)
pytest -v

# Verify Ed25519 benchmark receipts offline
python3 scripts/verify_ed25519_receipt.py \
  --public-key public_key_ed25519.pem \
  --jsonl-in logs/arm_b_live_receipts.jsonl \
  --require-zdr --require-zero-cost
```
