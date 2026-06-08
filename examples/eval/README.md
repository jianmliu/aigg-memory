# examples/eval — the behavioral-eval harness (MVP)

A runnable, deterministic implementation of [`docs/experiment_harness.md`](../../docs/experiment_harness.md):
the generic runner + a starter probe/verb library + a world adapter, so a new experiment is a
**manifest**, not a script.

```bash
python3 examples/eval/run.py examples/eval/experiments/memory_correctness_reconcile.json
python3 examples/eval/run.py examples/eval/experiments/mud_coordination_party.json
```

It needs **no real model and no network** — it starts a real `aigg-memory serve` and a tiny
**scripted stub model** (an OpenAI-compatible endpoint that replies from manifest rules), both
on localhost, then drives the cognition-under-test (plan / reconcile / reflect) over HTTP and
measures by reading the store files. Deterministic: same manifest → same verdict, every run.
Exits non-zero on failure (CI-friendly).

## Layout (mirrors the design's layering)

| file | role |
| --- | --- |
| `harness.py` | the generic, experiment-blind **runner** + `serve` subprocess + scripted **stub model** + the `Ctx` handed to verbs/probes |
| `verbs.py` | **verb** library — reusable host actions (store-setup `fact`/`goal`/`unit`; cognition `plan`/`reconcile`/`reflect`) |
| `probes.py` | **probe** library — read-only measurements over the corpora (`unit_status`/`unit_field`/`derived_from`/…) |
| `experiments/*.json` | **manifests** — pure data: `world`, `model_script`, `seed`, `steps`, `probes` (+ `expect`), `ablations` |
| `run.py` | entrypoint — runs the full condition + ablations, prints a report, sets the exit code |

## Adding an experiment

1. Write a manifest (data). 2. If you need a new measurement or action, add **one** probe to
`probes.py` or **one** verb to `verbs.py` — reusable by every later manifest. Nothing else
changes; the runner is shared.

## The first experiment: memory correctness

`memory_correctness_reconcile.json` validates a property the paper's append-only memory stream
could not have: when a supporting fact is superseded (the user moved Shanghai → Beijing),
`reconcile` archives the old fact with valid-time **and** stale-propagation flags the dependent
plan — with zero bespoke invalidation code. The `no_reconcile` ablation removes the step and the
runner asserts both outcomes **flip**, demonstrating the mechanism's necessity (the same
ablation method the paper used for believability, here on memory correctness, run as an exact
git-style re-run with diffed probe values).

## The mud sandbox: coordination by configuration

`mud_coordination_party.json` is Generative Agents' **coordination** emergence (Isabella's
Valentine party) expressed as config on the `mud` adapter — multiple NPCs, one corpus each.
The rails (`invite`/`announce_change` verbs) relay information with provenance; the cognition
(`plan`/`reconcile`) is the real kernel over HTTP; the multi-corpus probes measure from the
stores:

- `host_planned` — Isabella forms her party plan (real `/memory/plan`).
- `knew = 4` — **information diffusion**: every NPC learns about the party (via the relay).
- `intended = 2` — a *believable subset* form an attend-plan (one guest knows but doesn't).
- `stale_replan = 2` — when Isabella moves the time, `reconcile` + stale-propagation flag every
  dependent attend-plan **across NPCs** for replan, with zero bespoke code.
- `provenance = true` — every invite traces back to Isabella (earned, not hallucinated).

The `no_reconcile` ablation flips `stale_replan` to 0 (guests would show at the stale time).

## What's next (per the design doc)

Relationship-formation + information-diffusion manifests (same rails, new config), then the
full 25-agent Smallville config + ablation matrix, then **live mode** (a real host LLM sharing
the identical rails) — see [`docs/mud_sandbox_design.md`](../../docs/mud_sandbox_design.md).
