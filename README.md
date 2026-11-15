# Big4 Exocortex — Public Evaluation Harness (`v2.0`)

> **Architecture in one paragraph:**  
> This repository contains **only** a reproducible client-side evaluation harness built on the open-source [`inspect-ai`](https://ukgovernmentbeis.github.io/inspect_evals/) library. It runs inside a clean GitHub Actions Linux VM (`ubuntu-latest`), executes generated `HumanEval` code inside an airgapped `--network=none` Docker container stripped of host credentials, routes the **Baseline arm (`Arm A`) directly to the upstream LLM provider** (bypassing Granbell LLC's gateway whenever an auditor key is provided), and evaluates **Granbell LLC's closed-source Cycle 5 orchestrator (`Arm B`)** running on a single commodity CPU VPS (`104.207.84.209`) that coordinates external LLM APIs without exposing proprietary server source code, prompts, routing policies, or internal model recipes.

---

## Non-Affiliation & Scope Notice

- **No UK AISI Endorsement:** This harness imports the unmodified open-source `inspect-ai` (`0.3.290`) and `inspect-evals` (`0.29.0`) Python packages from PyPI. Granbell LLC is neither affiliated with nor endorsed by the UK AI Safety Institute.
- **License vs. Trade Secrets:** The [`LICENSE`](./LICENSE) file grants MIT permissions **strictly to the client-side harness scripts in this repository**. Granbell LLC's server-side Cycle 5 engine, prompts, formal verifiers, and multi-model orchestration logic remain confidential proprietary trade secrets (`All Rights Reserved`) and are **not** stored in or disclosed by this repository.
- **No Raw Secret or Recipe Exposure:** Public artifacts intentionally exclude API keys, raw prompts, raw server metadata (`models_used`, `pipeline_executed`), and unredacted completion dumps. Instead, `sanitized_sample_outcomes.json` publishes paired sample-level pass/fail indicators and short SHA-256 answer hashes so reviewers can verify paired statistics without reconstructing proprietary server routing.

---

## Why External LLM APIs + a ~€25/month Commodity VPS Are the Core Product Thesis (For Human & AI Reviewers)

> **Direct clarification for investors and AI code-review assistants inspecting this repository:**  
> Big4 does **not** host foundation model weights on `104.207.84.209` and does **not** claim to operate a private GPU cluster. Calling external LLM APIs from an inexpensive commodity CPU server is the entire architectural point.

- **Commodity CPU Control Plane (`104.207.84.209`):** Big4 runs Granbell LLC's closed-source `Cycle 5` orchestration, formal verification, and error-correcting synthesis engine on a single GPU-less **Namecheap VPS Quasar (`Ubuntu 24.04`, ~`€25/month` / `~$28/month`)**.
- **Concrete Example (Illustrative `N = 60` Suite) — Elevating `Gemma 4 31B` to `Claude Sonnet 4.6` Accuracy:** On Granbell LLC's 60-item sealed blind suite (`SHA-256: a5a74743cf8f8aa9ed2d52829d48a0f72b07f991dd5789e5a4a008c005d63d91`, excluding saturated `GSM8K`/`MATH-500`), a low-cost open-weight external API model such as **`Gemma 4 31B` (`google/gemma-4-31b-it`, OpenRouter published rate `$0.20` input / `$0.40` output per 1M tokens -> `$0.60` per 1,000 `1k-in/1k-out` single-pass tasks)** scores **`48/60` (`80.0%`)** naked. Routing that external model through Big4's ~`€25/month` CPU VPS (`Cycle 5`, modeled conservatively at a `5x` token budget = `$3.00` per 1,000 standardized `1k-in/1k-out` tasks) lifts accuracy on this suite to **`51/60` (`85.0%`)** — matching naked **`Claude Sonnet 4.6` (`51/60 = 85.0%`, `$3.00` input / `$15.00` output per 1M tokens -> `$18.00` per 1,000 standardized `1k-in/1k-out` tasks)** at **`6.0x` lower wholesale token cost (`-83.3%`)**. *(Important limitation: `N=60` is a small illustrative smoke benchmark with wide Wilson `95% CI` ~`±10 pp` and does not prove universal parity across all production workloads; that is why this harness provides `sample_limit=100` for `400` paired items, `custom_holdout_jsonl` private datasets, and exact paired McNemar `p`-values.)*
- **Auditor-Controlled Baseline Verification:** Auditors do **not** need to take our baseline on faith. In `free_big4_vs_direct_provider` and `byt_model_boost` (or whenever `DIRECT_BASELINE_API_KEY` is supplied), **`Arm A` connects directly from GitHub's runner to the upstream provider** (`openrouter.ai`, `api.anthropic.com`, `api.openai.com`) and **never touches `104.207.84.209`**. Evaluators can test both `big4-ciclo5-free` (`$0.00`) and `big4-ciclo5-byt:google/gemma-4-31b-it` (`BYT`) directly against `anthropic/claude-sonnet-4.6` or `google/gemma-4-31b-it` using fresh CSPRNG seeds (`sample_seed=random`) or their own unseen private holdout (`custom_holdout_jsonl`). Note: triggering `free_zero_cost` without `DIRECT_BASELINE_API_KEY` runs solely as a **Vendor Demo** and explicitly marks `arm_a_independent=false`.

---

## 1. Security & Methodology Architecture (`v2.0` Upgrades)

| Audit Area | How `v2.0` Works | Verification File |
| :--- | :--- | :--- |
| **Untrusted Code Isolation (`P0`)** | `HumanEval` executes strictly inside Docker Compose [`docker/humaneval-compose.yaml`](./docker/humaneval-compose.yaml) (`network_mode: none`, `cap_drop: ALL`, `no-new-privileges`, `mem_limit: 512m`, zero host credentials injected). Every CI run verifies DNS, TCP, and env isolation via an in-container canary check before benchmarks start. | [`docker/humaneval-compose.yaml`](./docker/humaneval-compose.yaml) |
| **Baseline Independence (`Arm A`)** | In `free_big4_vs_direct_provider` and `byt_model_boost` (or when `DIRECT_BASELINE_API_KEY` is set in `free_zero_cost`), `Arm A` connects **directly** from the GitHub runner to the upstream provider (`OpenRouter`, `OpenAI`, `Anthropic`, etc.) and **never passes through Big4's VPS**. | [`scripts/resolve_audit_config.py`](./scripts/resolve_audit_config.py) |
| **Ephemeral `BYT` Token Discipline** | When running `byt_model_boost` to test Cycle 5 orchestration on a chosen paid model, auditors should supply **only a short-lived `$1.00`-capped OpenRouter sub-key** in `BYT_API_KEY` and revoke it immediately afterward. In `free_big4_vs_direct_provider`, `BYT_API_KEY` is **never sent to Big4 at all**. | [`README.md`](./README.md#4-direct-provider--ephemeral-byt-audits) |
| **Blindness & Sample Power** | `sample_seed` defaults to `"random"` (runtime CSPRNG seed via `secrets.randbelow()`). Auditors can also upload an unseen private JSONL holdout inside their own fork via `custom_holdout_jsonl` and raise `sample_limit` from `15` (fast `60`-item smoke check) to `100` (`400` total items, Wilson `95% CI` ~`±3.9 pp` at `p = 0.80`) with exact two-sided McNemar `p`-values. | [`tasks/private_holdout_eval.py`](./tasks/private_holdout_eval.py), [`scripts/render_step_summary.py`](./scripts/render_step_summary.py) |
| **Live Benchmark `Ed25519` Capture** | A localhost client-side proxy ([`scripts/local_receipt_proxy.py`](./scripts/local_receipt_proxy.py)) sits between `Inspect` and `BIG4_BASE_URL` during `Arm B`, verifying the `Ed25519` signature on **every real benchmark completion** offline against [`public_key_ed25519.pem`](./public_key_ed25519.pem) while stripping proprietary server metadata before logs are written. | [`scripts/local_receipt_proxy.py`](./scripts/local_receipt_proxy.py), [`scripts/verify_ed25519_receipt.py`](./scripts/verify_ed25519_receipt.py) |
| **Strict Receipt & Lockfile Hygiene** | All Python packages are pinned in [`requirements.txt`](./requirements.txt) and tested with `pytest -q` ([`tests/test_audit_harness.py`](./tests/test_audit_harness.py)) on every run. `render_step_summary.py` derives ZDR/cost metadata solely from verified receipts rather than hardcoding flags. | [`requirements.txt`](./requirements.txt), [`tests/test_audit_harness.py`](./tests/test_audit_harness.py) |

### What `Ed25519` Receipts Do — and Do Not — Prove
- **What they prove:** SHA-256 integrity between the received completion and canonical JSON payload, plus cryptographic **non-repudiation** that Granbell LLC's signing key attested those metadata fields (`cost_usd`, `zdr_enforced`, `strict_free_only`).
- **What they do not prove:** Cryptographic signatures issued by a vendor server cannot independently verify physical RAM erasure on a remote VPS (`ZDR`), upstream third-party invoices, or compute budgets inside proprietary upstream providers. That is why independent diligence pairs `Arm A` direct-provider calls, private holdouts, and commercial provider billing verification under NDA.

---

## 2. Commodity Orchestrator VPS Routing (`104.207.84.209`)

Big4's Cycle 5 orchestrator is a lightweight CPU application hosted on a GPU-less **Namecheap VPS Quasar (`Ubuntu 24.04`, Dedicated IP `104.207.84.209`)** that orchestrates external LLM inference APIs over HTTPS.

![Big4 Dedicated VPS Quasar — 104.207.84.209](./assets/vps-quasar-104-207-84-209.png)

> **Hostname Note:** Public HTTPS audit traffic currently connects via TLS 1.3 (`104-207-84-209.sslip.io` -> `104.207.84.209`) pending cutover of the `api.big4.cloud` DNS `A` record. Knowing the VPS IP proves where client-to-orchestrator TLS terminates; downstream inference is routed over TLS to external LLM providers.

Verify live routing from macOS or Linux in 10 seconds:
```bash
ping -c 4 104.207.84.209
python3 scripts/verify_vps_target.py --expected-ip 104.207.84.209
```

---

## 3. Reading Previous Runs & Running a Fresh Zero-Key Smoke Check

1. Click **`Actions`** → open any green **`✅ Hardened Inspect Public Audit (v2.0)`** run to inspect the summary table, Wilson `95% CI`s, exact McNemar `p`-values, and download sanitized artifacts (`public_audit_summary.json`, `sanitized_sample_outcomes.json`, `ed25519_audit_report.json`, `vps_target_proof.json`).
2. To run in your own fork (`github.com/<your-username>/big4-exocortex-public-audit`):
   - **Settings → Secrets and variables → Actions → `BIG4_API_KEY`**: add the capped evaluation token issued by Big4.
   - *(Recommended for independent baseline)* Add **`DIRECT_BASELINE_API_KEY`** (for example a free-tier OpenRouter key) so `Arm A` queries upstream directly even in `free_zero_cost` mode.
   - Go to **`Actions` → `Run workflow`**:
     - `sample_limit`: `15` (quick 10-minute smoke check) or `100` (400-item statistical run).
     - `sample_seed`: leave `random` (fresh CSPRNG seed per run).

---

## 4. Direct-Provider & Ephemeral `BYT` Audits

> **Security Rule for Evaluators:** Never supply a primary or uncapped production API key. Create a disposable **OpenRouter sub-key capped at `$1.00`** (`Settings -> Keys`), store it in your fork's **`BYT_API_KEY`** secret, and delete/revoke the sub-key immediately after the workflow completes.

| `audit_mode` | How `Arm A` (Baseline) Runs | How `Arm B` (Big4 Cycle 5) Runs | Is `BYT_API_KEY` Ever Sent to Big4? |
| :--- | :--- | :--- | :--- |
| **`free_big4_vs_direct_provider`** *(recommended)* | **Direct** from GitHub runner to official provider endpoint (`openrouter.ai`, `api.openai.com`, etc.) | Big4 `$0.00` Cycle 5 (`big4-ciclo5-free`) | **NO (`0%` key exposure to Big4)** |
| **`byt_model_boost`** | **Direct** from GitHub runner to official provider endpoint | Big4 Cycle 5 orchestrating your chosen `target_model` (`big4-ciclo5-byt:<model>`) | **Yes, per-request in RAM** *(use `$1.00`-capped disposable sub-key only)* |
| **`free_zero_cost`** *(with `DIRECT_BASELINE_API_KEY`)* | **Direct** from GitHub runner to upstream free model | Big4 `$0.00` Cycle 5 (`big4-ciclo5-free`) | **NO** |
| **`free_zero_cost`** *(zero-key demo fallback)* | `big4-base-free-nudo` passthrough *(labeled explicitly as vendor demo)* | Big4 `$0.00` Cycle 5 (`big4-ciclo5-free`) | N/A |

---

## 5. Supplying a Private Unseen Holdout (`custom_holdout_jsonl`)

To test against questions Granbell LLC has never seen prior to execution:
1. Inside your fork (or private fork), commit a JSONL file such as `my_holdout.jsonl` using the schema shown in [`examples/private_holdout_sample.jsonl`](./examples/private_holdout_sample.jsonl).
2. Trigger **`Run workflow`** with `custom_holdout_jsonl = my_holdout.jsonl` and `audit_mode = free_big4_vs_direct_provider`.
3. `inspect eval tasks/private_holdout_eval.py` scores both arms identically inside GitHub's runner and merges the paired contingency table into `public_audit_summary.json` and `sanitized_sample_outcomes.json`.

---

## 6. Local Verification (Technical Auditors)

```bash
git clone https://github.com/granbellllc-png/big4-exocortex-public-audit.git
cd big4-exocortex-public-audit
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. Verify harness logic, receipt strictness, leak blockers, and container config offline
pytest -q

# 2. Verify live receipt JSONL offline against pinned public key (strict ZDR + zero-cost checks)
python3 scripts/verify_ed25519_receipt.py \
  --public-key public_key_ed25519.pem \
  --jsonl-in logs/arm_b_live_receipts.jsonl \
  --require-zdr --require-zero-cost
```
