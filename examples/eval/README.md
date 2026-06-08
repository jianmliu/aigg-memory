# examples/eval — the behavioral-eval harness (MVP)

A runnable, deterministic implementation of [`docs/experiment_harness.md`](../../docs/experiment_harness.md):
the generic runner + a starter probe/verb library + a world adapter, so a new experiment is a
**manifest**, not a script.

```bash
python3 examples/eval/run.py examples/eval/experiments/memory_correctness_reconcile.json
python3 examples/eval/run.py examples/eval/experiments/mud_coordination_party.json
python3 examples/eval/run.py examples/eval/experiments/information_diffusion.json
python3 examples/eval/run.py examples/eval/experiments/relationship_formation.json
python3 examples/eval/run.py examples/eval/experiments/mud_spacetime_party.json
python3 examples/eval/run.py examples/eval/smallville.py          # 25 agents, generated
```

An experiment file may be JSON (a static manifest) or a `.py` generator exposing `build()` —
at 25 agents you generate the hundreds of steps from compact config rather than hand-writing
them.

The last three reproduce Generative Agents' **three emergent behaviors** as configuration on
the `mud` adapter — same runner, different manifests:

| experiment | emergence | what it shows (all measured from the store) |
| --- | --- | --- |
| `mud_coordination_party` | **coordination** | host plans → invites diffuse → guests intend; a believable subset; a time-change replans every dependent plan (reconcile + stale) |
| `information_diffusion` | **information diffusion** | a rumor relays `sam→tom→jen→dan`; every copy traces to a teller who knew it; cutting one hop strands the chain |
| `relationship_formation` | **relationship formation** | encounters accrue `person_<id>` edges (network density), then `reflect` synthesizes a relationship belief; dropping a meeting drops the edge and the belief |
| `mud_spacetime_party` | **coordination, in space+time** | World (`move`/places) + Time (`tick`/`sleep`) rails: the invite diffuses only by **co-location**, intentions form only for those who learned, attendance needs being at the right **place at the right time** — the funnel `knew 3 > intended 2 > showed 1` emerges; a never-co-located NPC is simply left out |

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

## Scale: 25-agent Smallville + an ablation matrix

`smallville.py` generates a 25-agent / 12-tick run from compact config (seeded, so it replays
identically): each tick agents move to places and co-located pairs `meet` (network forms) and
sometimes gossip a single seeded rumor (`converse` + the conditional `relay`). It reproduces
the paper's headline figures and prints an ablation matrix:

```
   probe      full     no_conversation  no_encounters
   knew       12       1                12              # diffusion 1/25 -> 12/25 (~48%, paper ~48%)
   traceable  True     True             True            # every knower learned from a knower
   density    0.3833   0.3833           0.0             # network density (paper 0.167 -> ~0.74)
```

Cut conversation → the rumor never leaves its origin (knew 12→1); cut encounters → no network
(density →0). Same runner, a generator instead of a static manifest.

## What's next (per the design doc)

All three emergences pass deterministically — small (`mud_*`) and at scale (`smallville.py`),
each with ablations. Next: **live mode** (a real host LLM sharing the identical rails) — see
[`docs/mud_sandbox_design.md`](../../docs/mud_sandbox_design.md).
