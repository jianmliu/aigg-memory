#!/usr/bin/env python3
"""Run an aigg-memory behavioral-eval manifest.

    python3 examples/eval/run.py examples/eval/experiments/memory_correctness_reconcile.json

Starts a real `aigg-memory serve` + a scripted stub model (both on localhost, deterministic),
executes the manifest's seed + steps, samples the read-only probes over the store, evaluates
the pass predicates and the ablation flips, prints a report, and exits non-zero on failure.

No real model, no network, no kernel changes — only the public HTTP surface + reading the
store files. See docs/experiment_harness.md.
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # make harness/verbs/probes importable

from harness import run_experiment  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="aigg-eval-") as tmp:
        ok = run_experiment(manifest, Path(tmp))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
