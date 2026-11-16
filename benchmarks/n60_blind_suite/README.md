# N=60 Blind Evaluation Suite & Measured Telemetry Bundle (v2.1)

This directory contains the reproducible blind evaluation artifacts behind the Grid-1 (`$0.00` tier) and Grid-2 (Bring-Your-Own-Token BYOK ablation) numbers reported in the repository root.

## Contents

- `questions_n60_blind.json` — SHA-256 `05ab9e059daf42c20daf772e9fa42ea918490d91b3c422508702c99b23ad92a4`
  - 60 items evenly partitioned across MMLU-Pro (`15`), TruthfulQA MC1 (`15`), HumanEval / SWE-Patch (`15`), and GPQA Diamond (`15`).
- `ground_truth_n60_sealed.json` — SHA-256 `a5a74743cf8f8aa9ed2d52829d48a0f72b07f991dd5789e5a4a008c005d63d91`
  - Sealed ground-truth answer key used for automated post-run scoring.
- `measured_telemetry_and_ledger.json`
  - Per-arm scores, exact paired McNemar calculations (including the `k=3` `$0.00` matched-budget majority-vote ablation), measured `prompt_tokens` / `completion_tokens` / `wall_ms` / `cost_reported` per item, and sanitized OpenRouter wallet telemetry events.
- `qa_full_responses_n60.json`
  - All `60` prompts, expected ground truths, and sanitized verbatim model responses across `8` evaluated configurations (`base_free_nudo`, `big4_ciclo5_free`, `gemma4_31b_nudo`, `gemma4_31b_big4`, `claude_sonnet_4_6_nudo`, `claude_sonnet_4_6_big4`, `glm_5_3_nudo`, `glm_5_3_big4`) so external reviewers can inspect every individual failure and recovery (`MMLU_PRO_12`, `TRUTHFULQA_5`, `TRUTHFULQA_7`, `GPQA_DIAMOND_2`, `GPQA_DIAMOND_8` vs `TRUTHFULQA_3`, `TRUTHFULQA_11`, `GPQA_DIAMOND_3`, `GPQA_DIAMOND_9`, `GPQA_DIAMOND_13`).

## Key Empirical Context & Methodological Caveats

1. **Token Budget Asymmetry:**
   - Single-pass `google/gemma-4-31b-it` used `41,910` total tokens (`15,675` prompt / `26,235` completion; `$0.01167` OpenRouter cost; `48/60`).
   - Big4-orchestrated `google/gemma-4-31b-it` used `603,153` total tokens (`148,389` prompt / `454,764` completion — `17.33x` completion tokens, `$0.023126` OpenRouter wallet delta between `0.013113219` and `0.036238819`; `$0.2116` worst-case list ceiling at `$0.20/$0.40` per 1M tokens; `51/60`).
   - `claude-sonnet-4.6` single-pass used `41,062` total tokens (`16,195` prompt / `24,867` completion; `$0.42159` reported cost; `51/60`).
2. **Statistical Power at N=60 (`10` discordant items):**
   - `gemma4_31b_big4` and `claude_sonnet_4_6_nudo` both scored `51/60` (`85.0%`), agreeing on `50` items (`46` both pass, `4` both fail) and disagreeing on `10` items (`5` won only by Gemma+Big4, `5` won only by Sonnet single-pass; two-sided exact McNemar `p = 1.0`). At `N=60`, numerical parity (`51/60` vs `51/60`) is an empirical observation under specific token/harness conditions, NOT proof of universal architectural equivalence; larger private/CI holdouts and `--arm-a-epochs 3/5` (`--epochs-reducer mode`) are explicitly supported in v2.1 to test statistical superiority under matched compute budgets.
3. **Orchestration Transfer Limitation:**
   - Applying the Big4 multi-stage wrapper verbatim onto `claude-sonnet-4.6` **degraded** accuracy from `51/60` (`85.0%`) to `49/60` (`81.67%`, notably dropping GPQA Diamond), demonstrating empirically that verbose multi-stage verification prompts calibrated for open-weights models can over-constrain or induce self-doubt in frontier RLHF models.
4. **Telemetry Redaction:**
   - Internal orchestration trace fields (`models_used`, `pipeline_executed`, `consensus_type`, raw internal prompt templates) and the OpenRouter BYOK subkey prefix are stripped from `measured_telemetry_and_ledger.json`.
