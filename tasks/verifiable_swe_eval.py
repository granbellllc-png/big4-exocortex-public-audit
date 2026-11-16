"""
Deterministic-Oracle Python Bug-Repair Benchmark for Unmodified UK AISI Inspect.

Complements closed-book trivia suites by evaluating genuine stateful bug repair
under deterministic invariants (off-by-one boundaries, bitemporal lookahead I2,
RFC 6901 pointer unescaping, Decimal financial rounding, TTL+LRU eviction,
SemVer ordering, POSIX cron semantics, circuit-breaker state transitions, etc.).

Each task provides buggy starter code plus public docstring examples (`>>>`) in
the prompt, then evaluates model output against hidden assertions inside an
airgapped Docker Compose sandbox (`--network=none`, zero credentials).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Any, Dict, List

try:
    from inspect_ai import Task, task
    from inspect_ai.dataset import MemoryDataset, Sample
    from inspect_ai.scorer import CORRECT, INCORRECT, Score, Target, accuracy, scorer, stderr
    from inspect_ai.solver import TaskState, generate
    from inspect_ai.util import sandbox

    _INSPECT_AVAILABLE = True
except ImportError:  # pragma: no cover - local unit-test fallback when inspect-ai isn't in system python
    _INSPECT_AVAILABLE = False

    def task(fn: Any) -> Any:
        return fn

    def scorer(*_args: Any, **_kwargs: Any) -> Any:
        def _wrap(fn: Any) -> Any:
            return fn

        return _wrap

    def accuracy() -> Any:  # type: ignore[misc]
        return None

    def stderr() -> Any:  # type: ignore[misc]
        return None


SWE_REPAIR_SPECS: List[Dict[str, Any]] = [
    {
        "id": "swe_01_merge_intervals",
        "entry_point": "merge_closed_intervals",
        "buggy_code": (
            "def merge_closed_intervals(intervals):\n"
            "    out = []\n"
            "    for a, b in intervals:\n"
            "        if out and a < out[-1][1]:\n"
            "            out[-1] = (out[-1][0], b)\n"
            "        else:\n"
            "            out.append((a, b))\n"
            "    return out\n"
        ),
        "reference_code": (
            "def merge_closed_intervals(intervals):\n"
            "    if not intervals:\n"
            "        return []\n"
            "    ordered = sorted((min(a, b), max(a, b)) for a, b in intervals)\n"
            "    out = [ordered[0]]\n"
            "    for a, b in ordered[1:]:\n"
            "        prev_a, prev_b = out[-1]\n"
            "        if a <= prev_b:\n"
            "            out[-1] = (prev_a, max(prev_b, b))\n"
            "        else:\n"
            "            out.append((a, b))\n"
            "    return out\n"
        ),
        "prompt": (
            "Fix all bugs in `merge_closed_intervals(intervals)` so unsorted, touching (`a == prev_b`), "
            "and strictly nested intervals merge cleanly without losing bounds. Return complete runnable Python 3 code "
            "inside a ```python ... ``` fenced block.\n\n"
            "```python\n"
            "def merge_closed_intervals(intervals):\n"
            '    """Merge overlapping or touching closed integer intervals [(start, end), ...].\n'
            "    >>> merge_closed_intervals([(5, 7), (1, 3), (3, 5)])\n"
            "    [(1, 7)]\n"
            "    >>> merge_closed_intervals([(1, 10), (2, 4)])\n"
            "    [(1, 10)]\n"
            '    """\n'
            "    out = []\n"
            "    for a, b in intervals:\n"
            "        if out and a < out[-1][1]:\n"
            "            out[-1] = (out[-1][0], b)\n"
            "        else:\n"
            "            out.append((a, b))\n"
            "    return out\n"
            "```"
        ),
        "tests": (
            "assert merge_closed_intervals([]) == []\n"
            "assert merge_closed_intervals([(5, 7), (1, 3), (3, 5)]) == [(1, 7)]\n"
            "assert merge_closed_intervals([(1, 10), (2, 4), (6, 9)]) == [(1, 10)]\n"
            "assert merge_closed_intervals([(10, 12), (1, 2), (2, 3), (15, 16)]) == [(1, 3), (10, 12), (15, 16)]\n"
        ),
    },
    {
        "id": "swe_02_act360_decimal",
        "entry_point": "compute_act360_interest_cents",
        "buggy_code": (
            "def compute_act360_interest_cents(principal_cents: int, rate_bps: int, days: int) -> int:\n"
            "    if principal_cents < 0 or rate_bps < 0 or days < 0:\n"
            "        raise ValueError('negative input')\n"
            "    return int(round(principal_cents * (rate_bps / 10000.0) * (days / 360.0)))\n"
        ),
        "reference_code": (
            "from decimal import Decimal, ROUND_HALF_UP\n\n"
            "def compute_act360_interest_cents(principal_cents: int, rate_bps: int, days: int) -> int:\n"
            "    if principal_cents < 0 or rate_bps < 0 or days < 0:\n"
            "        raise ValueError('negative input')\n"
            "    num = Decimal(principal_cents) * Decimal(rate_bps) * Decimal(days)\n"
            "    den = Decimal(10000) * Decimal(360)\n"
            "    return int((num / den).quantize(Decimal('1'), rounding=ROUND_HALF_UP))\n"
        ),
        "prompt": (
            "Fix binary float rounding and banker's half-even rounding bugs in `compute_act360_interest_cents`: "
            "ACT/360 exact interest in integer cents must use exact rational/Decimal arithmetic with `ROUND_HALF_UP` "
            "(ties `.5` always round up away from zero). Return complete Python 3 code in a ```python ... ``` block.\n\n"
            "```python\n"
            "def compute_act360_interest_cents(principal_cents: int, rate_bps: int, days: int) -> int:\n"
            '    """Compute ACT/360 interest in integer cents using exact ROUND_HALF_UP.\n'
            "    >>> compute_act360_interest_cents(100000, 360, 5)\n"
            "    50\n"
            "    >>> compute_act360_interest_cents(10000, 180, 1)\n"
            "    1\n"
            '    """\n'
            "    if principal_cents < 0 or rate_bps < 0 or days < 0:\n"
            "        raise ValueError('negative input')\n"
            "    return int(round(principal_cents * (rate_bps / 10000.0) * (days / 360.0)))\n"
            "```"
        ),
        "tests": (
            "assert compute_act360_interest_cents(100000, 360, 5) == 50\n"
            "assert compute_act360_interest_cents(10000, 180, 1) == 1\n"
            "assert compute_act360_interest_cents(30000, 180, 1) == 2\n"
            "assert compute_act360_interest_cents(0, 500, 90) == 0\n"
            "try:\n"
            "    compute_act360_interest_cents(-1, 100, 10)\n"
            "    raise AssertionError('must reject negative')\n"
            "except ValueError:\n"
            "    pass\n"
        ),
    },
    {
        "id": "swe_03_kahn_toposort",
        "entry_point": "topological_sort_lex",
        "buggy_code": (
            "def topological_sort_lex(nodes, edges):\n"
            "    indeg = {u: 0 for u in nodes}\n"
            "    adj = {u: [] for u in nodes}\n"
            "    for u, v in edges:\n"
            "        adj[u].append(v)\n"
            "        indeg[v] += 1\n"
            "    q = [u for u in nodes if indeg[u] == 0]\n"
            "    out = []\n"
            "    while q:\n"
            "        u = q.pop(0)\n"
            "        out.append(u)\n"
            "        for v in adj[u]:\n"
            "            indeg[v] -= 1\n"
            "            if indeg[v] == 0:\n"
            "                q.append(v)\n"
            "    return out\n"
        ),
        "reference_code": (
            "import heapq\n\n"
            "def topological_sort_lex(nodes, edges):\n"
            "    node_set = list(dict.fromkeys(nodes))\n"
            "    indeg = {u: 0 for u in node_set}\n"
            "    adj = {u: [] for u in node_set}\n"
            "    for u, v in edges:\n"
            "        adj[u].append(v)\n"
            "        indeg[v] += 1\n"
            "    heap = [u for u in node_set if indeg[u] == 0]\n"
            "    heapq.heapify(heap)\n"
            "    out = []\n"
            "    while heap:\n"
            "        u = heapq.heappop(heap)\n"
            "        out.append(u)\n"
            "        for v in adj[u]:\n"
            "            indeg[v] -= 1\n"
            "            if indeg[v] == 0:\n"
            "                heapq.heappush(heap, v)\n"
            "    return out if len(out) == len(node_set) else None\n"
        ),
        "prompt": (
            "Fix `topological_sort_lex(nodes, edges)` so it returns the lexicographically smallest "
            "valid topological order on `nodes` given directed edges `(u, v)`, and returns `None` when any cycle exists. "
            "Return complete Python 3 code inside ```python ... ```.\n\n"
            "```python\n"
            "def topological_sort_lex(nodes, edges):\n"
            '    """Return lexicographically smallest topological sort or None on cycle.\n'
            "    >>> topological_sort_lex(['c', 'a', 'b'], [('c', 'b')])\n"
            "    ['a', 'c', 'b']\n"
            "    >>> topological_sort_lex(['a', 'b'], [('a', 'b'), ('b', 'a')]) is None\n"
            "    True\n"
            '    """\n'
            "    return []\n"
            "```"
        ),
        "tests": (
            "assert topological_sort_lex(['c', 'a', 'b'], [('c', 'b')]) == ['a', 'c', 'b']\n"
            "assert topological_sort_lex(['a', 'b'], [('a', 'b'), ('b', 'a')]) is None\n"
            "assert topological_sort_lex(['z', 'b', 'a', 'm'], [('z', 'a'), ('b', 'm')]) == ['b', 'm', 'z', 'a']\n"
            "assert topological_sort_lex([], []) == []\n"
        ),
    },
    {
        "id": "swe_04_ttl_lru_cache",
        "entry_point": "TTLLRUCache",
        "buggy_code": (
            "class TTLLRUCache:\n"
            "    def __init__(self, capacity: int, ttl_ms: int):\n"
            "        self.capacity = capacity\n"
            "        self.ttl_ms = ttl_ms\n"
            "        self.data = {}\n\n"
            "    def get(self, key, now_ms: int):\n"
            "        if key not in self.data:\n"
            "            return None\n"
            "        val, exp = self.data[key]\n"
            "        return val\n\n"
            "    def put(self, key, value, now_ms: int) -> None:\n"
            "        if len(self.data) >= self.capacity:\n"
            "            oldest = next(iter(self.data))\n"
            "            del self.data[oldest]\n"
            "        self.data[key] = (value, now_ms + self.ttl_ms)\n"
        ),
        "reference_code": (
            "from collections import OrderedDict\n\n"
            "class TTLLRUCache:\n"
            "    def __init__(self, capacity: int, ttl_ms: int):\n"
            "        self.capacity = max(0, int(capacity))\n"
            "        self.ttl_ms = int(ttl_ms)\n"
            "        self.data = OrderedDict()\n\n"
            "    def _purge(self, now_ms: int) -> None:\n"
            "        expired = [k for k, (_, exp) in self.data.items() if now_ms >= exp]\n"
            "        for k in expired:\n"
            "            del self.data[k]\n\n"
            "    def get(self, key, now_ms: int):\n"
            "        self._purge(now_ms)\n"
            "        if key not in self.data:\n"
            "            return None\n"
            "        val, exp = self.data[key]\n"
            "        self.data.move_to_end(key)\n"
            "        return val\n\n"
            "    def put(self, key, value, now_ms: int) -> None:\n"
            "        self._purge(now_ms)\n"
            "        if self.capacity <= 0:\n"
            "            return\n"
            "        if key in self.data:\n"
            "            self.data.move_to_end(key)\n"
            "        elif len(self.data) >= self.capacity:\n"
            "            self.data.popitem(last=False)\n"
            "        self.data[key] = (value, now_ms + self.ttl_ms)\n"
        ),
        "prompt": (
            "Fix `TTLLRUCache(capacity, ttl_ms)`: items expire strictly when `now_ms >= inserted_at + ttl_ms`, "
            "expired items must be purged BEFORE capacity LRU eviction on `put`, and `get` refreshes LRU recency ONLY for live entries. "
            "Updating an existing key refreshes its value, expiration, and recency without evicting another live entry. "
            "Return complete Python 3 code inside ```python ... ```.\n\n"
            "```python\n"
            "class TTLLRUCache:\n"
            '    """LRU cache with TTL expiration at now_ms >= created_at + ttl_ms.\n'
            "    >>> c = TTLLRUCache(2, 100)\n"
            "    >>> c.put('a', 1, 0); c.put('b', 2, 50); c.get('a', 60)\n"
            "    1\n"
            "    >>> c.put('c', 3, 70); (c.get('a', 70), c.get('b', 70))\n"
            "    (1, None)\n"
            "    >>> c.get('a', 100) is None\n"
            "    True\n"
            '    """\n'
            "    def __init__(self, capacity: int, ttl_ms: int):\n"
            "        self.capacity = capacity\n"
            "        self.ttl_ms = ttl_ms\n"
            "        self.data = {}\n"
            "```"
        ),
        "tests": (
            "c = TTLLRUCache(2, 100)\n"
            "c.put('a', 1, 0)\n"
            "c.put('b', 2, 50)\n"
            "assert c.get('a', 60) == 1\n"
            "c.put('c', 3, 70)\n"
            "assert c.get('a', 70) == 1 and c.get('b', 70) is None\n"
            "assert c.get('a', 100) is None\n"
            "# Putting key 'd' at t=110: 'a' is already expired, 'c' is live -> 'c' MUST NOT be evicted!\n"
            "c.put('d', 4, 110)\n"
            "assert c.get('c', 110) == 3 and c.get('d', 110) == 4\n"
            "c.put('c', 30, 120)\n"
            "assert c.get('c', 180) == 30 and c.get('d', 180) == 4\n"
        ),
    },
    {
        "id": "swe_05_bitemporal_lookup",
        "entry_point": "bitemporal_point_in_time",
        "buggy_code": (
            "def bitemporal_point_in_time(rows, as_of: int, know_at: int):\n"
            "    eligible = [r for r in rows if r['t_eff'] <= as_of]\n"
            "    if not eligible:\n"
            "        return None\n"
            "    best = max(eligible, key=lambda r: (r['t_eff'], r['t_rec']))\n"
            "    return best['val']\n"
        ),
        "reference_code": (
            "def bitemporal_point_in_time(rows, as_of: int, know_at: int):\n"
            "    eligible = [r for r in rows if r['t_eff'] <= as_of and r['t_rec'] <= know_at]\n"
            "    if not eligible:\n"
            "        return None\n"
            "    best = max(enumerate(eligible), key=lambda p: (p[1]['t_eff'], p[1]['t_rec'], p[0]))[1]\n"
            "    return best['val']\n"
        ),
        "prompt": (
            "Fix lookahead leakage in `bitemporal_point_in_time(rows, as_of, know_at)`: only records inside the bitemporal cone "
            "`t_eff <= as_of` AND `t_rec <= know_at` may be read; pick highest `(t_eff, t_rec, list_index)` or return `None`. "
            "Return complete Python 3 code inside ```python ... ```.\n\n"
            "```python\n"
            "def bitemporal_point_in_time(rows, as_of: int, know_at: int):\n"
            '    """Return value valid at effective time <= as_of as known at record time <= know_at.\n'
            "    >>> r = [{'t_eff': 10, 't_rec': 12, 'val': 'v1'}, {'t_eff': 15, 't_rec': 30, 'val': 'v2'}]\n"
            "    >>> bitemporal_point_in_time(r, as_of=20, know_at=25)\n"
            "    'v1'\n"
            '    """\n'
            "    eligible = [x for x in rows if x['t_eff'] <= as_of]\n"
            "    return max(eligible, key=lambda x: x['t_eff'])['val'] if eligible else None\n"
            "```"
        ),
        "tests": (
            "rows = [\n"
            "    {'t_eff': 10, 't_rec': 12, 'val': 'v1'},\n"
            "    {'t_eff': 15, 't_rec': 30, 'val': 'v2_future_correction'},\n"
            "    {'t_eff': 10, 't_rec': 20, 'val': 'v1_restated'},\n"
            "]\n"
            "assert bitemporal_point_in_time(rows, 20, 15) == 'v1'\n"
            "assert bitemporal_point_in_time(rows, 20, 25) == 'v1_restated'\n"
            "assert bitemporal_point_in_time(rows, 20, 30) == 'v2_future_correction'\n"
            "assert bitemporal_point_in_time(rows, 9, 100) is None\n"
            "assert bitemporal_point_in_time(rows, 20, 11) is None\n"
        ),
    },
    {
        "id": "swe_06_token_bucket",
        "entry_point": "TokenBucket",
        "buggy_code": (
            "class TokenBucket:\n"
            "    def __init__(self, rate_per_sec: float, capacity: float, start_ts: float = 0.0):\n"
            "        self.rate = rate_per_sec\n"
            "        self.capacity = capacity\n"
            "        self.tokens = capacity\n"
            "        self.last_ts = start_ts\n\n"
            "    def allow(self, now_ts: float, cost: float = 1.0) -> bool:\n"
            "        self.tokens = min(self.capacity, self.tokens + int((now_ts - self.last_ts) * self.rate))\n"
            "        self.last_ts = now_ts\n"
            "        if self.tokens >= cost:\n"
            "            self.tokens -= cost\n"
            "            return True\n"
            "        return False\n"
        ),
        "reference_code": (
            "class TokenBucket:\n"
            "    def __init__(self, rate_per_sec: float, capacity: float, start_ts: float = 0.0):\n"
            "        self.rate = float(rate_per_sec)\n"
            "        self.capacity = float(capacity)\n"
            "        self.tokens = float(capacity)\n"
            "        self.last_ts = float(start_ts)\n\n"
            "    def allow(self, now_ts: float, cost: float = 1.0) -> bool:\n"
            "        if cost < 0:\n"
            "            raise ValueError('negative cost')\n"
            "        if now_ts > self.last_ts:\n"
            "            self.tokens = min(self.capacity, self.tokens + (now_ts - self.last_ts) * self.rate)\n"
            "            self.last_ts = float(now_ts)\n"
            "        if self.tokens + 1e-12 >= cost:\n"
            "            self.tokens = max(0.0, self.tokens - cost)\n"
            "            return True\n"
            "        return False\n"
        ),
        "prompt": (
            "Fix `TokenBucket`: sub-unit fractional refills must accumulate across high-frequency calls (do not `int(...)` truncate), "
            "and backward timestamp jitter (`now_ts < self.last_ts`) must NOT subtract tokens or move `last_ts` backwards. "
            "Reject `cost < 0` with `ValueError`. Return complete Python 3 code inside ```python ... ```.\n\n"
            "```python\n"
            "class TokenBucket:\n"
            '    """Monotonic continuous-refill token bucket rate limiter.\n'
            "    >>> tb = TokenBucket(rate_per_sec=2.0, capacity=2.0, start_ts=0.0)\n"
            "    >>> (tb.allow(0.0, 2.0), tb.allow(0.25, 1.0), tb.allow(0.5, 1.0))\n"
            "    (True, False, True)\n"
            '    """\n'
            "    def __init__(self, rate_per_sec: float, capacity: float, start_ts: float = 0.0):\n"
            "        self.rate = rate_per_sec\n"
            "        self.capacity = capacity\n"
            "        self.tokens = capacity\n"
            "        self.last_ts = start_ts\n"
            "```"
        ),
        "tests": (
            "tb = TokenBucket(rate_per_sec=2.0, capacity=2.0, start_ts=0.0)\n"
            "assert tb.allow(0.0, 2.0) is True\n"
            "assert tb.allow(0.25, 1.0) is False  # +0.5 tokens\n"
            "assert tb.allow(0.50, 1.0) is True   # +0.5 -> 1.0 total\n"
            "assert tb.allow(0.10, 0.5) is False  # backward ts must not break state\n"
            "assert tb.allow(0.75, 0.5) is True   # +0.5 -> 0.5 tokens available -> True\n"
        ),
    },
    {
        "id": "swe_07_semver_sort",
        "entry_point": "sort_semver_versions",
        "buggy_code": (
            "def sort_semver_versions(versions):\n"
            "    return sorted(versions, key=lambda s: [int(x) for x in s.split('-')[0].split('.')])\n"
        ),
        "reference_code": (
            "def _semver_key(ver: str):\n"
            "    core_pre = ver.split('+', 1)[0]\n"
            "    if '-' in core_pre:\n"
            "        core, pre = core_pre.split('-', 1)\n"
            "        pre_parts = [\n"
            "            (0, int(p)) if p.isdigit() else (1, p)\n"
            "            for p in pre.split('.')\n"
            "        ]\n"
            "        has_pre = 0\n"
            "    else:\n"
            "        core = core_pre\n"
            "        pre_parts = []\n"
            "        has_pre = 1\n"
            "    major, minor, patch = (int(x) for x in core.split('.'))\n"
            "    return (major, minor, patch, has_pre, pre_parts)\n\n"
            "def sort_semver_versions(versions):\n"
            "    return sorted(versions, key=_semver_key)\n"
        ),
        "prompt": (
            "Fix `sort_semver_versions(versions)` to follow SemVer 2.0.0 precedence: strip `+build` metadata, sort `X.Y.Z` numerically, "
            "pre-release versions precede release (`1.0.0-alpha < 1.0.0`), numeric pre-release identifiers sort as integers and ALWAYS precede "
            "alphanumeric ones (`1.0.0-2 < 1.0.0-10 < 1.0.0-alpha`), and preserve stability. Return complete Python 3 code inside ```python ... ```.\n\n"
            "```python\n"
            "def sort_semver_versions(versions):\n"
            '    """Sort SemVer 2.0.0 strings in ascending precedence.\n'
            "    >>> sort_semver_versions(['1.0.0', '1.0.0-alpha', '1.0.0-2', '1.0.0-10'])\n"
            "    ['1.0.0-2', '1.0.0-10', '1.0.0-alpha', '1.0.0']\n"
            '    """\n'
            "    return sorted(versions)\n"
            "```"
        ),
        "tests": (
            "assert sort_semver_versions(['1.0.0', '1.0.0-alpha', '1.0.0-2', '1.0.0-10']) == ['1.0.0-2', '1.0.0-10', '1.0.0-alpha', '1.0.0']\n"
            "assert sort_semver_versions(['1.0.0-alpha.1', '1.0.0-alpha', '1.0.0-alpha.beta', '1.0.0-beta']) == ['1.0.0-alpha', '1.0.0-alpha.1', '1.0.0-alpha.beta', '1.0.0-beta']\n"
            "assert sort_semver_versions(['2.10.0+exp.sha', '2.2.0', '2.1.9-rc.1']) == ['2.1.9-rc.1', '2.2.0', '2.10.0+exp.sha']\n"
        ),
    },
    {
        "id": "swe_08_hamilton_cents",
        "entry_point": "allocate_pro_rata_cents",
        "buggy_code": (
            "def allocate_pro_rata_cents(total_cents: int, weights):\n"
            "    s = sum(weights)\n"
            "    return [int(total_cents * w / s) for w in weights]\n"
        ),
        "reference_code": (
            "def allocate_pro_rata_cents(total_cents: int, weights):\n"
            "    if total_cents < 0:\n"
            "        raise ValueError('negative total_cents')\n"
            "    if not weights:\n"
            "        return []\n"
            "    if any(w < 0 for w in weights):\n"
            "        raise ValueError('negative weight')\n"
            "    total_w = sum(weights)\n"
            "    if total_w <= 0:\n"
            "        raise ValueError('positive total weight required')\n"
            "    floors = [(total_cents * w) // total_w for w in weights]\n"
            "    rems = [(total_cents * w) % total_w for w in weights]\n"
            "    leftover = total_cents - sum(floors)\n"
            "    order = sorted(range(len(weights)), key=lambda i: (-rems[i], i))\n"
            "    out = list(floors)\n"
            "    for i in order[:leftover]:\n"
            "        out[i] += 1\n"
            "    return out\n"
        ),
        "prompt": (
            "Fix `allocate_pro_rata_cents(total_cents, weights)` using Hamilton's largest-remainder apportionment in exact integer arithmetic "
            "over integer `weights >= 0` so `sum(out) == total_cents` ALWAYS, breaking remainder ties by earliest index. Return complete Python 3 code in ```python ... ```.\n\n"
            "```python\n"
            "def allocate_pro_rata_cents(total_cents: int, weights):\n"
            '    """Allocate exact integer cents across non-negative weights via Hamilton largest remainder.\n'
            "    >>> allocate_pro_rata_cents(100, [1, 1, 1])\n"
            "    [34, 33, 33]\n"
            '    """\n'
            "    s = sum(weights)\n"
            "    return [int(total_cents * w / s) for w in weights]\n"
            "```"
        ),
        "tests": (
            "assert allocate_pro_rata_cents(100, [1, 1, 1]) == [34, 33, 33]\n"
            "assert allocate_pro_rata_cents(10, [1, 2, 3]) == [2, 3, 5]\n"
            "assert allocate_pro_rata_cents(0, [5, 10]) == [0, 0]\n"
            "assert allocate_pro_rata_cents(7, [0, 3, 3]) == [0, 4, 3]\n"
        ),
    },
    {
        "id": "swe_09_rfc6901_pointer",
        "entry_point": "resolve_json_pointer",
        "buggy_code": (
            "def resolve_json_pointer(doc, pointer: str):\n"
            "    if not pointer:\n"
            "        return doc\n"
            "    cur = doc\n"
            "    for raw in pointer.lstrip('/').split('/'):\n"
            "        key = raw.replace('~0', '~').replace('~1', '/')\n"
            "        if isinstance(cur, list):\n"
            "            cur = cur[int(key)]\n"
            "        else:\n"
            "            cur = cur[key]\n"
            "    return cur\n"
        ),
        "reference_code": (
            "def resolve_json_pointer(doc, pointer: str):\n"
            "    if pointer == '':\n"
            "        return doc\n"
            "    if not pointer.startswith('/'):\n"
            "        raise ValueError('pointer must start with /')\n"
            "    cur = doc\n"
            "    for raw in pointer[1:].split('/'):\n"
            "        key = raw.replace('~1', '/').replace('~0', '~')\n"
            "        if isinstance(cur, list):\n"
            "            if not (key == '0' or (key.isdigit() and not key.startswith('0'))):\n"
            "                raise KeyError(key)\n"
            "            idx = int(key)\n"
            "            if idx >= len(cur):\n"
            "                raise IndexError(idx)\n"
            "            cur = cur[idx]\n"
            "        elif isinstance(cur, dict):\n"
            "            if key not in cur:\n"
            "                raise KeyError(key)\n"
            "            cur = cur[key]\n"
            "        else:\n"
            "            raise TypeError('non-container')\n"
            "    return cur\n"
        ),
        "prompt": (
            "Fix RFC 6901 JSON Pointer bugs in `resolve_json_pointer(doc, pointer)`: unescape `~1` -> `/` BEFORE `~0` -> `~` "
            "(so `'~01'` resolves to `'~1'`, NOT `'/'`), reject leading-zero array indices like `'01'` (`KeyError` or `ValueError`), "
            "and require empty string `''` for root or leading `'/'`. Return complete Python 3 code in ```python ... ```.\n\n"
            "```python\n"
            "def resolve_json_pointer(doc, pointer: str):\n"
            '    """Resolve RFC 6901 JSON Pointer cleanly.\n'
            "    >>> resolve_json_pointer({'a/b': {'~1': 42}}, '/a~1b/~01')\n"
            "    42\n"
            '    """\n'
            "    return doc\n"
            "```"
        ),
        "tests": (
            "assert resolve_json_pointer({'a/b': {'~1': 42}}, '/a~1b/~01') == 42\n"
            "assert resolve_json_pointer({'': [10, 20]}, '//1') == 20\n"
            "assert resolve_json_pointer({'x': 1}, '') == {'x': 1}\n"
            "failed = False\n"
            "try:\n"
            "    resolve_json_pointer([10, 20], '/01')\n"
            "except (KeyError, ValueError):\n"
            "    failed = True\n"
            "assert failed\n"
        ),
    },
    {
        "id": "swe_10_linear_quantile",
        "entry_point": "linear_quantile",
        "buggy_code": (
            "def linear_quantile(values, q: float) -> float:\n"
            "    values.sort()\n"
            "    return float(values[int(q * (len(values) - 1))])\n"
        ),
        "reference_code": (
            "def linear_quantile(values, q: float) -> float:\n"
            "    if not values or not (0.0 <= q <= 1.0):\n"
            "        raise ValueError('invalid input')\n"
            "    s = sorted(values)\n"
            "    if len(s) == 1:\n"
            "        return float(s[0])\n"
            "    pos = q * (len(s) - 1)\n"
            "    lo = int(pos)\n"
            "    hi = min(lo + 1, len(s) - 1)\n"
            "    frac = pos - lo\n"
            "    return float(s[lo] + (s[hi] - s[lo]) * frac)\n"
        ),
        "prompt": (
            "Fix `linear_quantile(values, q)` so it NEVER mutates caller's `values` list, validates non-empty sequence and `0 <= q <= 1`, "
            "and uses linear interpolation between bracketing sorted elements. Return complete Python 3 code in ```python ... ```.\n\n"
            "```python\n"
            "def linear_quantile(values, q: float) -> float:\n"
            '    """Compute q in [0, 1] linear-interpolated quantile without mutating caller input.\n'
            "    >>> linear_quantile([40, 10, 20, 30], 0.5)\n"
            "    25.0\n"
            '    """\n'
            "    values.sort()\n"
            "    return float(values[int(q * (len(values) - 1))])\n"
            "```"
        ),
        "tests": (
            "orig = [40, 10, 20, 30]\n"
            "assert linear_quantile(orig, 0.5) == 25.0\n"
            "assert orig == [40, 10, 20, 30]\n"
            "assert abs(linear_quantile([10, 20, 30, 40], 0.25) - 17.5) < 1e-9\n"
            "assert linear_quantile([7], 0.9) == 7.0\n"
        ),
    },
    {
        "id": "swe_11_canonical_query_sig",
        "entry_point": "canonical_query_string",
        "buggy_code": (
            "def canonical_query_string(params):\n"
            "    return '&'.join(f'{k}={v}' for k, v in sorted(params, key=lambda x: x[0]))\n"
        ),
        "reference_code": (
            "from urllib.parse import quote\n\n"
            "def canonical_query_string(params) -> str:\n"
            "    encoded = [\n"
            "        (quote(str(k), safe='-._~'), quote(str(v), safe='-._~'))\n"
            "        for k, v in params\n"
            "    ]\n"
            "    encoded.sort()\n"
            "    return '&'.join(f'{k}={v}' for k, v in encoded)\n"
        ),
        "prompt": (
            "Fix `canonical_query_string(params)` for AWS/HMAC-style SigV4 canonical queries: RFC 3986 percent-encode keys and values "
            "(leaving `-._~` unencoded, spaces as `%20`, never `+`), then sort pairs lexicographically by `(encoded_key, encoded_val)`. "
            "Return complete Python 3 code in ```python ... ```.\n\n"
            "```python\n"
            "def canonical_query_string(params) -> str:\n"
            '    """Return RFC 3986 sorted canonical query string over (key, value) pairs.\n'
            "    >>> canonical_query_string([('b', '2'), ('a', 'hello world'), ('b', '10')])\n"
            "    'a=hello%20world&b=10&b=2'\n"
            '    """\n'
            "    return '&'.join(f'{k}={v}' for k, v in sorted(params, key=lambda x: x[0]))\n"
            "```"
        ),
        "tests": (
            "assert canonical_query_string([('b', '2'), ('a', 'hello world'), ('b', '10')]) == 'a=hello%20world&b=10&b=2'\n"
            "assert canonical_query_string([('x~1', 'a/b+c')]) == 'x~1=a%2Fb%2Bc'\n"
            "assert canonical_query_string([]) == ''\n"
        ),
    },
    {
        "id": "swe_12_posix_cron_match",
        "entry_point": "cron_matches",
        "buggy_code": (
            "def _field_match(expr, val, lo, hi):\n"
            "    return expr == '*' or int(expr) == val\n\n"
            "def cron_matches(expr: str, minute: int, hour: int, dom: int, month: int, dow: int) -> bool:\n"
            "    m, h, dm, mo, dw = expr.split()\n"
            "    return (_field_match(m, minute, 0, 59) and _field_match(h, hour, 0, 23)\n"
            "            and _field_match(dm, dom, 1, 31) and _field_match(mo, month, 1, 12)\n"
            "            and _field_match(dw, dow, 0, 6))\n"
        ),
        "reference_code": (
            "def _parse_cron_field(expr: str, lo: int, hi: int):\n"
            "    vals = set()\n"
            "    for part in expr.split(','):\n"
            "        if '/' in part:\n"
            "            base, step_s = part.split('/', 1)\n"
            "            step = int(step_s)\n"
            "        else:\n"
            "            base, step = part, 1\n"
            "        if step <= 0:\n"
            "            raise ValueError('step must be positive')\n"
            "        if base == '*':\n"
            "            a, b = lo, hi\n"
            "        elif '-' in base:\n"
            "            a_s, b_s = base.split('-', 1)\n"
            "            a, b = int(a_s), int(b_s)\n"
            "        else:\n"
            "            a = int(base)\n"
            "            b = hi if '/' in part else a\n"
            "        if a > b:\n"
            "            raise ValueError('invalid range')\n"
            "        vals.update(range(a, b + 1, step))\n"
            "    return vals\n\n"
            "def cron_matches(expr: str, minute: int, hour: int, dom: int, month: int, dow: int) -> bool:\n"
            "    m_s, h_s, dm_s, mo_s, dw_s = expr.strip().split()\n"
            "    if minute not in _parse_cron_field(m_s, 0, 59):\n"
            "        return False\n"
            "    if hour not in _parse_cron_field(h_s, 0, 23):\n"
            "        return False\n"
            "    if month not in _parse_cron_field(mo_s, 1, 12):\n"
            "        return False\n"
            "    norm_dow = 0 if dow == 7 else dow\n"
            "    dw_vals = {0 if v == 7 else v for v in _parse_cron_field(dw_s, 0, 7)}\n"
            "    dm_vals = _parse_cron_field(dm_s, 1, 31)\n"
            "    if dm_s != '*' and dw_s != '*':\n"
            "        return (dom in dm_vals) or (norm_dow in dw_vals)\n"
            "    return (dom in dm_vals) and (norm_dow in dw_vals)\n"
        ),
        "prompt": (
            "Fix `cron_matches(expr, minute, hour, dom, month, dow)` to support comma lists, ranges `a-b`, steps `*/k` / `a-b/k`, "
            "Sunday `dow` normalized (`0` or `7`), AND POSIX `dom`/`dow` semantics: when BOTH day-of-month and day-of-week are non-`*`, "
            "the schedule matches if EITHER `dom` OR `dow` matches. Return complete Python 3 code in ```python ... ```.\n\n"
            "```python\n"
            "def cron_matches(expr: str, minute: int, hour: int, dom: int, month: int, dow: int) -> bool:\n"
            '    """Evaluate 5-field POSIX cron match.\n'
            "    >>> cron_matches('*/15 9-17 1 * 1', 30, 10, 15, 6, 1)\n"
            "    True\n"
            "    >>> cron_matches('0 0 15 * 5', 0, 0, 15, 3, 2)\n"
            "    True\n"
            '    """\n'
            "    return False\n"
            "```"
        ),
        "tests": (
            "assert cron_matches('*/15 9-17 1 * 1', 30, 10, 15, 6, 1) is True\n"
            "assert cron_matches('0 0 15 * 5', 0, 0, 15, 3, 2) is True\n"
            "assert cron_matches('0,30 8-10 * 1-6 0', 30, 9, 12, 3, 7) is True\n"
            "assert cron_matches('0 12 10 * 5', 0, 12, 11, 3, 4) is False\n"
            "assert cron_matches('5/20 * * * *', 45, 0, 1, 1, 1) is True\n"
        ),
    },
    {
        "id": "swe_13_circuit_breaker",
        "entry_point": "CircuitBreaker",
        "buggy_code": (
            "class CircuitBreaker:\n"
            "    def __init__(self, failure_threshold: int, cooldown_ms: int):\n"
            "        self.state = 'CLOSED'\n"
            "        self.failures = 0\n\n"
            "    def allow(self, now_ms: int) -> bool:\n"
            "        return self.state == 'CLOSED'\n\n"
            "    def record(self, ok: bool, now_ms: int) -> None:\n"
            "        if ok:\n"
            "            self.failures = 0\n"
            "        else:\n"
            "            self.failures += 1\n"
        ),
        "reference_code": (
            "class CircuitBreaker:\n"
            "    def __init__(self, failure_threshold: int, cooldown_ms: int):\n"
            "        self.failure_threshold = max(1, int(failure_threshold))\n"
            "        self.cooldown_ms = max(0, int(cooldown_ms))\n"
            "        self.state = 'CLOSED'\n"
            "        self.failures = 0\n"
            "        self.opened_at = None\n"
            "        self.probe_in_flight = False\n\n"
            "    def allow(self, now_ms: int) -> bool:\n"
            "        if self.state == 'CLOSED':\n"
            "            return True\n"
            "        if self.state == 'OPEN':\n"
            "            if self.opened_at is not None and (now_ms - self.opened_at) >= self.cooldown_ms:\n"
            "                self.state = 'HALF_OPEN'\n"
            "                self.probe_in_flight = True\n"
            "                return True\n"
            "            return False\n"
            "        if not self.probe_in_flight:\n"
            "            self.probe_in_flight = True\n"
            "            return True\n"
            "        return False\n\n"
            "    def record(self, ok: bool, now_ms: int) -> None:\n"
            "        self.probe_in_flight = False\n"
            "        if ok:\n"
            "            self.state = 'CLOSED'\n"
            "            self.failures = 0\n"
            "            self.opened_at = None\n"
            "            return\n"
            "        if self.state == 'HALF_OPEN':\n"
            "            self.state = 'OPEN'\n"
            "            self.opened_at = now_ms\n"
            "            return\n"
            "        self.failures += 1\n"
            "        if self.failures >= self.failure_threshold:\n"
            "            self.state = 'OPEN'\n"
            "            self.opened_at = now_ms\n"
        ),
        "prompt": (
            "Fix `CircuitBreaker(failure_threshold, cooldown_ms)` state machine: trips `CLOSED -> OPEN` after `failure_threshold` consecutive failures; "
            "after `cooldown_ms`, a single `allow(now_ms)` transitions `OPEN -> HALF_OPEN` and permits ONE probe (`probe_in_flight`); "
            "probe success resets to `CLOSED`, probe failure immediately returns to `OPEN` for another full `cooldown_ms`. "
            "Return complete Python 3 code inside ```python ... ```.\n\n"
            "```python\n"
            "class CircuitBreaker:\n"
            '    """Three-state circuit breaker CLOSED / OPEN / HALF_OPEN.\n'
            "    >>> cb = CircuitBreaker(2, 1000)\n"
            "    >>> cb.record(False, 0); cb.record(False, 10); (cb.state, cb.allow(500), cb.allow(1010))\n"
            "    ('OPEN', False, True)\n"
            '    """\n'
            "    def __init__(self, failure_threshold: int, cooldown_ms: int):\n"
            "        self.state = 'CLOSED'\n"
            "```"
        ),
        "tests": (
            "cb = CircuitBreaker(2, 1000)\n"
            "assert cb.allow(0) is True\n"
            "cb.record(False, 0)\n"
            "assert cb.state == 'CLOSED'\n"
            "cb.record(False, 10)\n"
            "assert cb.state == 'OPEN'\n"
            "assert cb.allow(500) is False\n"
            "assert cb.allow(1010) is True and cb.state == 'HALF_OPEN'\n"
            "assert cb.allow(1011) is False  # only 1 probe allowed while HALF_OPEN probe in flight\n"
            "cb.record(False, 1020)\n"
            "assert cb.state == 'OPEN' and cb.allow(1500) is False\n"
            "assert cb.allow(2020) is True\n"
            "cb.record(True, 2030)\n"
            "assert cb.state == 'CLOSED' and cb.failures == 0\n"
        ),
    },
    {
        "id": "swe_14_irregular_ema",
        "entry_point": "irregular_ema",
        "buggy_code": (
            "def irregular_ema(points, half_life: float):\n"
            "    ema = points[0][1]\n"
            "    for _, val in points[1:]:\n"
            "        ema = 0.5 * ema + 0.5 * val\n"
            "    return float(ema)\n"
        ),
        "reference_code": (
            "def irregular_ema(points, half_life: float) -> float:\n"
            "    if not points or half_life <= 0:\n"
            "        raise ValueError('invalid input')\n"
            "    ordered = sorted(points, key=lambda p: p[0])\n"
            "    prev_t, ema = ordered[0][0], float(ordered[0][1])\n"
            "    for ts, val in ordered[1:]:\n"
            "        dt = ts - prev_t\n"
            "        decay = 0.5 ** (dt / half_life)\n"
            "        ema = decay * ema + (1.0 - decay) * float(val)\n"
            "        prev_t = ts\n"
            "    return ema\n"
        ),
        "prompt": (
            "Fix `irregular_ema(points, half_life)` over `(timestamp, value)` observations: sort by timestamp if out of order, "
            "then decay prior EMA by `0.5 ** (dt / half_life)` per interval. Validate non-empty `points` and `half_life > 0`. "
            "Return complete Python 3 code in ```python ... ```.\n\n"
            "```python\n"
            "def irregular_ema(points, half_life: float) -> float:\n"
            '    """Continuous-time half-life EMA over irregular (ts, val) observations.\n'
            "    >>> round(irregular_ema([(0.0, 0.0), (10.0, 100.0)], half_life=10.0), 4)\n"
            "    50.0\n"
            "    >>> round(irregular_ema([(0.0, 0.0), (20.0, 100.0)], half_life=10.0), 4)\n"
            "    75.0\n"
            '    """\n'
            "    return 0.0\n"
            "```"
        ),
        "tests": (
            "assert abs(irregular_ema([(0.0, 0.0), (10.0, 100.0)], 10.0) - 50.0) < 1e-9\n"
            "assert abs(irregular_ema([(20.0, 100.0), (0.0, 0.0)], 10.0) - 75.0) < 1e-9\n"
            "assert abs(irregular_ema([(5.0, 42.0)], 3.0) - 42.0) < 1e-9\n"
        ),
    },
    {
        "id": "swe_15_dedupe_latest",
        "entry_point": "dedupe_keep_latest",
        "buggy_code": (
            "def dedupe_keep_latest(pairs):\n"
            "    seen = set()\n"
            "    out = []\n"
            "    for k, v in pairs:\n"
            "        if k not in seen:\n"
            "            seen.add(k)\n"
            "            out.append((k, v))\n"
            "    return out\n"
        ),
        "reference_code": (
            "def dedupe_keep_latest(pairs):\n"
            "    seen = set()\n"
            "    rev = []\n"
            "    for k, v in reversed(pairs):\n"
            "        if k not in seen:\n"
            "            seen.add(k)\n"
            "            rev.append((k, v))\n"
            "    rev.reverse()\n"
            "    return rev\n"
        ),
        "prompt": (
            "Fix `dedupe_keep_latest(pairs)` so when key `k` appears multiple times, only its LAST `(k, v)` entry is kept, "
            "ordered by the position of its LAST occurrence. Return complete Python 3 code in ```python ... ```.\n\n"
            "```python\n"
            "def dedupe_keep_latest(pairs):\n"
            '    """Keep only the last (key, value) per key, ordered by last occurrence.\n'
            "    >>> dedupe_keep_latest([('a', 1), ('b', 2), ('a', 3)])\n"
            "    [('b', 2), ('a', 3)]\n"
            '    """\n'
            "    return pairs\n"
            "```"
        ),
        "tests": (
            "assert dedupe_keep_latest([('a', 1), ('b', 2), ('a', 3)]) == [('b', 2), ('a', 3)]\n"
            "assert dedupe_keep_latest([('x', 1), ('y', 2), ('z', 3), ('x', 9), ('y', 8)]) == [('z', 3), ('x', 9), ('y', 8)]\n"
            "assert dedupe_keep_latest([]) == []\n"
        ),
    },
    {
        "id": "swe_16_markdown_fences",
        "entry_point": "count_closed_code_blocks",
        "buggy_code": (
            "def count_closed_code_blocks(markdown_text: str) -> int:\n"
            "    ticks = sum(1 for ln in markdown_text.splitlines() if ln.strip().startswith('```'))\n"
            "    return -1 if ticks % 2 else ticks // 2\n"
        ),
        "reference_code": (
            "import re\n\n"
            "def count_closed_code_blocks(markdown_text: str) -> int:\n"
            "    fence_len = 0\n"
            "    fence_char = ''\n"
            "    blocks = 0\n"
            "    for line in markdown_text.splitlines():\n"
            "        stripped = line.lstrip(' ')\n"
            "        if fence_len == 0:\n"
            "            m = re.match(r'^(`{3,}|~{3,})', stripped)\n"
            "            if m:\n"
            "                fence_char = m.group(1)[0]\n"
            "                fence_len = len(m.group(1))\n"
            "        else:\n"
            "            m = re.match(r'^(' + re.escape(fence_char) + r'{3,})\\s*$', stripped)\n"
            "            if m and len(m.group(1)) >= fence_len:\n"
            "                fence_len = 0\n"
            "                fence_char = ''\n"
            "                blocks += 1\n"
            "    return -1 if fence_len > 0 else blocks\n"
        ),
        "prompt": (
            "Fix `count_closed_code_blocks(markdown_text)` following CommonMark fenced-block rules: an outer 4-backtick block ```` ```` ```` "
            "or `~~~` block must NOT be closed early by an inner 3-backtick ```` ``` ```` line (requires same char and length >= opening fence with no info string). "
            "Return `-1` if the final fence remains unclosed, else the top-level closed block count. Return Python 3 code in ```python ... ```.\n\n"
            "```python\n"
            "def count_closed_code_blocks(markdown_text: str) -> int:\n"
            '    """Count closed top-level CommonMark fenced code blocks (-1 if unclosed).\n'
            "    >>> count_closed_code_blocks('````md\\n```py\\nx=1\\n```\\n````')\n"
            "    1\n"
            '    """\n'
            "    return 0\n"
            "```"
        ),
        "tests": (
            "assert count_closed_code_blocks('````md\\n```py\\nx=1\\n```\\n````') == 1\n"
            "assert count_closed_code_blocks('```py\\na=1\\n```\\n~~~sh\\necho hi\\n~~~') == 2\n"
            "assert count_closed_code_blocks('```py\\nx = 1') == -1\n"
            "assert count_closed_code_blocks('````\\n```\\n````\\n```\\nok\\n```') == 2\n"
        ),
    },
    {
        "id": "swe_17_parse_duration",
        "entry_point": "parse_duration_ms",
        "buggy_code": (
            "def parse_duration_ms(spec: str) -> int:\n"
            "    if spec.endswith('s'):\n"
            "        return int(float(spec[:-1]) * 1000)\n"
            "    return int(spec)\n"
        ),
        "reference_code": (
            "import re\n\n"
            "_TOKEN_RE = re.compile(r'(\\d+(?:\\.\\d+)?)(ms|us|s|m|h|d)')\n"
            "_MULT_MS = {'us': 0.001, 'ms': 1.0, 's': 1000.0, 'm': 60000.0, 'h': 3600000.0, 'd': 86400000.0}\n\n"
            "def parse_duration_ms(spec: str) -> int:\n"
            "    compact = ''.join(spec.split())\n"
            "    if not compact:\n"
            "        raise ValueError('empty duration')\n"
            "    pos = 0\n"
            "    total_ms = 0.0\n"
            "    for m in _TOKEN_RE.finditer(compact):\n"
            "        if m.start() != pos:\n"
            "            raise ValueError(f'unexpected syntax in {spec!r}')\n"
            "        total_ms += float(m.group(1)) * _MULT_MS[m.group(2)]\n"
            "        pos = m.end()\n"
            "    if pos != len(compact):\n"
            "        raise ValueError(f'trailing garbage in {spec!r}')\n"
            "    return int(round(total_ms))\n"
        ),
        "prompt": (
            "Fix `parse_duration_ms(spec)` to parse compound duration strings containing whitespace and fractional units "
            "(`us`, `ms`, `s`, `m`, `h`, `d`), returning rounded integer milliseconds and raising `ValueError` on empty or malformed/negative strings. "
            "Return complete Python 3 code in ```python ... ```.\n\n"
            "```python\n"
            "def parse_duration_ms(spec: str) -> int:\n"
            '    """Parse compound duration string into integer milliseconds.\n'
            "    >>> parse_duration_ms('1h 30m 250ms')\n"
            "    5400250\n"
            "    >>> parse_duration_ms('1.5s')\n"
            "    1500\n"
            '    """\n'
            "    return 0\n"
            "```"
        ),
        "tests": (
            "assert parse_duration_ms('1h 30m 250ms') == 5400250\n"
            "assert parse_duration_ms('1.5s') == 1500\n"
            "assert parse_duration_ms('2m500ms') == 120500\n"
            "assert parse_duration_ms('1d') == 86400000\n"
            "bad = False\n"
            "try:\n"
            "    parse_duration_ms('-5s')\n"
            "except ValueError:\n"
            "    bad = True\n"
            "assert bad\n"
        ),
    },
    {
        "id": "swe_18_max_drawdown",
        "entry_point": "max_drawdown_ratio",
        "buggy_code": (
            "def max_drawdown_ratio(equity_curve) -> float:\n"
            "    return max(0.0, (equity_curve[0] - equity_curve[-1]) / equity_curve[0])\n"
        ),
        "reference_code": (
            "def max_drawdown_ratio(equity_curve) -> float:\n"
            "    if not equity_curve:\n"
            "        return 0.0\n"
            "    peak = equity_curve[0]\n"
            "    max_dd = 0.0\n"
            "    for val in equity_curve[1:]:\n"
            "        if val > peak:\n"
            "            peak = val\n"
            "        elif peak > 0:\n"
            "            dd = (peak - val) / peak\n"
            "            if dd > max_dd:\n"
            "                max_dd = dd\n"
            "    return float(max_dd)\n"
        ),
        "prompt": (
            "Fix `max_drawdown_ratio(equity_curve)` to compute maximum peak-to-trough fractional drawdown `(peak - trough) / peak` "
            "over the curve (returning `0.0` on empty/monotonic/zero-peak curves). Do not assume peak occurs at index 0. "
            "Return complete Python 3 code in ```python ... ```.\n\n"
            "```python\n"
            "def max_drawdown_ratio(equity_curve) -> float:\n"
            '    """Compute maximum peak-to-trough drawdown fraction in [0.0, 1.0+].\n'
            "    >>> max_drawdown_ratio([100, 150, 90, 140])\n"
            "    0.4\n"
            '    """\n'
            "    return 0.0\n"
            "```"
        ),
        "tests": (
            "assert abs(max_drawdown_ratio([100, 150, 90, 140]) - 0.4) < 1e-9\n"
            "assert max_drawdown_ratio([100, 120, 150]) == 0.0\n"
            "assert max_drawdown_ratio([]) == 0.0\n"
            "assert abs(max_drawdown_ratio([100, 200, 50, 300, 210]) - 0.75) < 1e-9\n"
        ),
    },
    {
        "id": "swe_19_merkle_leaf_diff",
        "entry_point": "diff_sorted_leaves",
        "buggy_code": (
            "def diff_sorted_leaves(old_leaves, new_leaves):\n"
            "    old_k = {k for k, _ in old_leaves}\n"
            "    new_k = {k for k, _ in new_leaves}\n"
            "    return {'added': sorted(new_k - old_k), 'removed': sorted(old_k - new_k), 'modified': []}\n"
        ),
        "reference_code": (
            "def diff_sorted_leaves(old_leaves, new_leaves):\n"
            "    added, removed, modified = [], [], []\n"
            "    i, j = 0, 0\n"
            "    while i < len(old_leaves) and j < len(new_leaves):\n"
            "        ok, oh = old_leaves[i]\n"
            "        nk, nh = new_leaves[j]\n"
            "        if ok == nk:\n"
            "            if oh != nh:\n"
            "                modified.append(ok)\n"
            "            i += 1\n"
            "            j += 1\n"
            "        elif ok < nk:\n"
            "            removed.append(ok)\n"
            "            i += 1\n"
            "        else:\n"
            "            added.append(nk)\n"
            "            j += 1\n"
            "    while i < len(old_leaves):\n"
            "        removed.append(old_leaves[i][0])\n"
            "        i += 1\n"
            "    while j < len(new_leaves):\n"
            "        added.append(new_leaves[j][0])\n"
            "        j += 1\n"
            "    return {'added': added, 'removed': removed, 'modified': modified}\n"
        ),
        "prompt": (
            "Fix `diff_sorted_leaves(old_leaves, new_leaves)` over sorted unique `(key, digest)` pairs so it returns "
            "`{'added': [...], 'removed': [...], 'modified': [...]}` with exact digest comparison on shared keys. "
            "Return complete Python 3 code in ```python ... ```.\n\n"
            "```python\n"
            "def diff_sorted_leaves(old_leaves, new_leaves):\n"
            '    """Diff two sorted unique (key, digest) sequences.\n'
            "    >>> diff_sorted_leaves([('a', '1'), ('b', '2')], [('b', '9'), ('c', '3')])\n"
            "    {'added': ['c'], 'removed': ['a'], 'modified': ['b']}\n"
            '    """\n'
            "    return {'added': [], 'removed': [], 'modified': []}\n"
            "```"
        ),
        "tests": (
            "assert diff_sorted_leaves([('a', '1'), ('b', '2')], [('b', '9'), ('c', '3')]) == {'added': ['c'], 'removed': ['a'], 'modified': ['b']}\n"
            "assert diff_sorted_leaves([('x', 'h')], [('x', 'h'), ('y', 'z')]) == {'added': ['y'], 'removed': [], 'modified': []}\n"
            "assert diff_sorted_leaves([], []) == {'added': [], 'removed': [], 'modified': []}\n"
        ),
    },
    {
        "id": "swe_20_banach_fixed_point",
        "entry_point": "verify_banach_contraction",
        "buggy_code": (
            "def verify_banach_contraction(residuals, tol: float = 1e-6) -> bool:\n"
            "    ratios = [residuals[i] / residuals[i - 1] for i in range(1, len(residuals))]\n"
            "    return max(ratios) < 1.0\n"
        ),
        "reference_code": (
            "def verify_banach_contraction(residuals, tol: float = 1e-6) -> bool:\n"
            "    if not residuals or residuals[-1] > tol:\n"
            "        return False\n"
            "    if len(residuals) == 1:\n"
            "        return residuals[0] <= tol\n"
            "    has_non_degenerate = False\n"
            "    for i in range(1, len(residuals)):\n"
            "        prev, cur = residuals[i - 1], residuals[i]\n"
            "        if prev < 0 or cur < 0:\n"
            "            return False\n"
            "        if prev <= tol:\n"
            "            if cur > tol:\n"
            "                return False\n"
            "            continue\n"
            "        has_non_degenerate = True\n"
            "        if cur >= prev:\n"
            "            return False\n"
            "    return has_non_degenerate or residuals[-1] <= tol\n"
        ),
        "prompt": (
            "Fix `verify_banach_contraction(residuals, tol=1e-6)`: verify that non-negative residual sequence converges below `tol` "
            "(`residuals[-1] <= tol`) with strict monotone contraction (`cur < prev` whenever `prev > tol`), safely handling exact zero steps "
            "without `ZeroDivisionError` and handling length-1 sequences (`residuals[0] <= tol`). Return complete Python 3 code in ```python ... ```.\n\n"
            "```python\n"
            "def verify_banach_contraction(residuals, tol: float = 1e-6) -> bool:\n"
            '    """Verify strict contraction above tol and terminal convergence <= tol.\n'
            "    >>> verify_banach_contraction([1.0, 0.4, 0.1, 0.0, 0.0], tol=1e-6)\n"
            "    True\n"
            "    >>> verify_banach_contraction([1.0, 0.5, 0.25], tol=1e-6)\n"
            "    False\n"
            '    """\n'
            "    return False\n"
            "```"
        ),
        "tests": (
            "assert verify_banach_contraction([1.0, 0.4, 0.1, 0.0, 0.0], 1e-6) is True\n"
            "assert verify_banach_contraction([1.0, 0.5, 0.25], 1e-6) is False\n"
            "assert verify_banach_contraction([0.0], 1e-6) is True\n"
            "assert verify_banach_contraction([0.5, 0.6, 0.0], 1e-6) is False\n"
            "assert verify_banach_contraction([], 1e-6) is False\n"
        ),
    },
]

assert len(SWE_REPAIR_SPECS) == 20


def extract_python_code(raw: str) -> str:
    """Extract candidate Python 3 block cleanly from model output."""
    text = raw or ""
    closed = re.findall(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.S | re.I)
    if closed:
        return closed[-1].rstrip()
    unclosed = re.search(r"```(?:python|py)?\s*\n(.+)$", text, flags=re.S | re.I)
    if unclosed:
        return re.sub(r"```+\s*$", "", unclosed.group(1)).rstrip()
    return text.strip()


def run_spec_tests_local(spec: Dict[str, Any], candidate_code: str, timeout_sec: int = 5) -> tuple[bool, str]:
    """Isolated local verifier used by pytest regression checks."""
    script = f"{candidate_code}\n\n{spec['tests']}\nprint('PASS')\n"
    proc = subprocess.run(
        [sys.executable, "-I", "-"],
        input=script,
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    ok = proc.returncode == 0 and "PASS" in proc.stdout
    return ok, (proc.stderr or proc.stdout).strip()


@scorer(metrics=[accuracy(), stderr()])
def swe_sandbox_scorer():
    async def score(state: TaskState, target: Target) -> Score:
        code = extract_python_code(state.output.completion or "")
        test_block = (state.metadata or {}).get("tests", "") or target.text
        script = f"{code}\n\n{test_block}\nprint('PASS_SWE_SANDBOX')\n"
        result = await sandbox().exec(
            cmd=["python3", "-I", "-"],
            input=script,
            timeout=15,
        )
        passed = bool(result.success and "PASS_SWE_SANDBOX" in (result.stdout or ""))
        return Score(
            value=CORRECT if passed else INCORRECT,
            answer=code,
            explanation="Passed all sandbox invariant assertions" if passed else (result.stderr or result.stdout or "Failed assertions")[:500],
        )

    return score


@task
def verifiable_swe_repair() -> Any:
    if not _INSPECT_AVAILABLE:  # pragma: no cover
        raise RuntimeError("inspect_ai is required to instantiate verifiable_swe_repair() Task.")
    samples = [
        Sample(
            id=spec["id"],
            input=spec["prompt"],
            target=spec["tests"],
            metadata={"entry_point": spec["entry_point"], "tests": spec["tests"]},
        )
        for spec in SWE_REPAIR_SPECS
    ]
    dataset = MemoryDataset(samples=samples, name="verifiable_swe_repair")
    compose_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "docker", "humaneval-compose.yaml")
    return Task(
        dataset=dataset,
        solver=generate(),
        scorer=swe_sandbox_scorer(),
        sandbox=("docker", compose_path) if os.path.isfile(compose_path) else "docker",
    )
