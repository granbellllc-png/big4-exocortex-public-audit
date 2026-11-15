# Big4 Exocortex — Zero-Trust Public Audit (UK AI Safety Institute `Inspect`)

This public repository runs an **unmodified third-party benchmark evaluation** on neutral GitHub-hosted Linux virtual machines (`ubuntu-latest`) against a capped, Zero-Data-Retention (ZDR) OpenAI-compatible endpoint backed by a ~€28/month GPU-less VPS.

### Why this audit exists
Self-hosted benchmark reports can always face skepticism (*"Did you write your own grading script or cherry-pick outputs locally?"*). Here:
1. **Neutral Execution Environment:** All evaluations run inside an ephemeral, clean Microsoft/GitHub Actions `ubuntu-latest` runner.
2. **Official Government Grader Only:** This repo installs `inspect-ai` and `inspect-evals` (**UK AI Safety Institute**) directly from PyPI and downloads untouched public datasets (`MMLU-Pro`, `TruthfulQA`, `GPQA Diamond`, `HumanEval`). Zero custom grading code is used.
3. **Naked vs. Orthogonal Cycle 5 at `$0.00`:** The exact same job tests:
   - `openai-api/big4/big4-base-free-nudo` — single-pass `$0.00` baseline
   - `openai-api/big4/big4-ciclo5-free` — `$0.00` orthogonal matrix interception + local Python sandbox
4. **Offline Cryptographic Verification (`Ed25519`):** Five live responses are verified offline against the pinned public key in [`public_key_ed25519.pem`](./public_key_ed25519.pem).
5. **Zero Trade Secrets Exposed:** No server infrastructure code, matrix weights, internal routing tables, or provider credentials live in this repository. External endpoint settings remain encrypted inside repository Action Secrets.

---

### Come leggerlo in italiano
Questo repository pubblico esegue su **macchina virtuale neutrale GitHub Actions** il framework ufficiale **Inspect del UK AI Safety Institute** (scaricato intatto da PyPI con i dataset ufficiali `MMLU-Pro`, `TruthfulQA`, `GPQA Diamond` e `HumanEval`), mettendo a confronto nello stesso job il modello base `$0.00` nudo e la pipeline `Big4 Cycle 5` a costo token `$0.00`, più verifica crittografica offline `Ed25519`, senza esporre alcun codice proprietario né IP del server.

### Reproducing via Fork
Any external reviewer can **Fork** this repository, configure `BIG4_BASE_URL` and a capped `BIG4_API_KEY` audit token in **Settings → Secrets and variables → Actions**, and trigger `.github/workflows/uk-aisi-public-audit.yml` directly via `workflow_dispatch`.
