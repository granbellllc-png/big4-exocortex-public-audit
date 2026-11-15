"""
Private / Custom Holdout Evaluation Task for Unmodified UK AISI Inspect.

Allows institutional auditors or investors to supply an unseen private `.jsonl`
dataset inside their own repository fork without sharing questions with Granbell
LLC before evaluation.

Supported JSONL record schemas:
  1. Multiple choice:
     {"id": "q1", "input": "Question text", "choices": ["optA", "optB", "optC", "optD"], "target": "B"}
  2. Exact/numeric text match:
     {"id": "q2", "input": "Compute 17 * 23.", "target": "391", "numeric": true}
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.scorer import choice, match
from inspect_ai.solver import generate, multiple_choice


def load_jsonl_samples(dataset_path: str) -> tuple[List[Sample], bool, bool]:
    path = os.path.abspath(dataset_path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Custom holdout JSONL file not found: {dataset_path}")

    samples: List[Sample] = []
    has_mc = False
    all_numeric = True
    with open(path, "r", encoding="utf-8") as fh:
        for idx, raw_line in enumerate(fh, 1):
            line = raw_line.strip()
            if not line:
                continue
            row: Dict[str, Any] = json.loads(line)
            sid = row.get("id") or f"holdout_{idx}"
            question = row.get("input") or row.get("question") or row.get("prompt")
            target = row.get("target") if row.get("target") is not None else row.get("answer")
            if question is None or target is None:
                raise ValueError(f"Record {idx} in {dataset_path} must contain 'input' and 'target'")
            choices = row.get("choices")
            if choices is not None:
                if not isinstance(choices, list) or len(choices) < 2:
                    raise ValueError(f"Record {idx} 'choices' must be a list of >= 2 options")
                has_mc = True
            if not row.get("numeric"):
                all_numeric = False
            samples.append(
                Sample(
                    id=str(sid),
                    input=str(question),
                    choices=[str(c) for c in choices] if choices else None,
                    target=str(target),
                    metadata=row.get("metadata") if isinstance(row.get("metadata"), dict) else {},
                )
            )

    if not samples:
        raise ValueError(f"No samples loaded from {dataset_path}")
    if has_mc and not all(s.choices for s in samples):
        raise ValueError("Do not mix multiple-choice and free-text records in a single holdout file")
    return samples, has_mc, all_numeric


@task
def private_holdout(dataset_path: str = "examples/private_holdout_sample.jsonl") -> Task:
    samples, has_mc, all_numeric = load_jsonl_samples(dataset_path)
    dataset = MemoryDataset(samples=samples, name="private_holdout")
    if has_mc:
        return Task(dataset=dataset, solver=multiple_choice(), scorer=choice())
    return Task(dataset=dataset, solver=generate(), scorer=match(location="end", ignore_case=True, numeric=all_numeric))
