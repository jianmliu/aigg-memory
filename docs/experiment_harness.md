# Experiment harness — an extensible design for aigg-memory behavioral evals

> The three emergence experiments ([`mud_emergence_eval.md`](mud_emergence_eval.md)) are the
> *first* of many. This spec is the framework that makes the **N-th** experiment cost a
> single declarative manifest, not a bespoke script. Status: design. Date: 2026-06-08.

## 1. The extensibility problem

A one-off eval script bakes setup, run loop, measurement, and pass criteria into one file.
The second experiment copies it; the fifth is unmaintainable; an ablation forks the whole
thing. We instead want: **the runner is shared and experiment-agnostic; an experiment is
data + a few small reusable hooks.** Adding one should touch *only* a manifest (and maybe one
new probe), never the loop.

Three design moves make that possible, each leaning on something aigg-memory already gives:

1. **Measurement = read-only queries over the git-versioned corpora, decoupled from the run.**
   Memory is inspectable typed markdown + a queryable index, so a metric is a function of the
   *store state*, sampled after the fact — never instrumentation threaded through the loop.
   Adding a metric never touches execution.
2. **Execution = composition of a fixed verb set over the public endpoints.** Experiments
   compose reusable host verbs (`converse`, `relay`, `invite`, `sleep`, `announce_change`)
   and kernel ops (`observe`/`dream`/`recall`); they don't reimplement them.
3. **Replay & ablation = git, not forks.** Each tick commits; `restore(ref)` re-runs from any
   point; an ablation is a config delta on the dream pipeline, branched from the same restore
   point and **diffed**.

## 2. Layering (where new code goes — and doesn't)

```
┌ aigg-memory kernel ────────────────  unchanged; HTTP/CLI only (no eval code in the kernel)
├ Probe library ─────────────────────  read-only queries over corpora (reusable across experiments)
├ World adapter ─────────────────────  supplies agents, clock, and VERBS (action); pluggable
│     • mud        — live MUD host (LLM dialogue + world + action)
│     • headless   — scripted stimuli, no dialogue LLM (deterministic kernel-correctness runs)
├ Experiment manifest ───────────────  DATA: seed, stimulus schedule, probes, pass, ablations
├ Runner ────────────────────────────  generic: ticks the clock, fires stimuli/sleeps, samples
│                                        probes, commits per tick, emits a structured report
└ Registry + report/compare ─────────  discovers manifests; runs ablation matrices; diffs vs bands
```

The kernel stays infra-free; the harness is a **separate layer that only speaks HTTP/CLI**.
A new experiment lands in the *manifest* row. A new measurement lands in *probe library* (one
pure function). A new world (not a MUD) lands in *world adapter*. Nothing below changes.

## 3. The Experiment manifest (declarative)

```jsonc
{
  "id": "coordination_party",
  "name": "Coordination — Isabella's Valentine's party",
  "claim": "A party emerges from goal->belief->plan + invite-relay; attendance rests on a live plan.",
  "references": { "paper": "arXiv:2304.03442 §coordination", "approx": { "knew": 12, "showed": 5 } },

  "world": {
    "adapter": "mud",                       // or "headless"
    "agents": "fixtures/smallville/agents/", // personas + initial corpora as DATA, not code
    "clock":  { "start": "2026-02-13T08:00", "step": "PT1H", "until": "2026-02-14T20:00" }
  },

  "seed": [                                  // declarative initial conditions (kernel writes)
    { "op": "goal",   "agent": "isabella", "slug": "goal_host_party", "locked": true,
      "description": "Host a Valentine's party so neighbours connect" },
    { "op": "fact",   "agent": "isabella", "slug": "event_valentine_party",
      "description": "Valentine's party at Hobbs Cafe, Feb 14 5pm" }
  ],

  "schedule": [                              // sim-time-keyed stimuli (reusable verbs)
    { "at": "2026-02-13T10:00", "verb": "converse", "args": { "a": "isabella", "b": "maria", "topic": "the party" } },
    { "at": "2026-02-13T22:00", "verb": "sleep",    "args": { "agents": "*", "deep": true } },
    { "at": "2026-02-14T12:00", "verb": "announce_change",
      "args": { "agent": "isabella", "slug": "event_valentine_party", "to": "Hobbs Cafe, Feb 14 5:30pm" } }
  ],

  "probes": [                                // read-only measurements over the store
    { "id": "diffusion", "probe": "diffusion",    "args": { "matcher": "valentine party" }, "at": "every" },
    { "id": "density",   "probe": "relationship_density", "at": "every" },
    { "id": "intended",  "probe": "active_plan_fraction", "args": { "matcher": "attend party", "at": "2026-02-14T17:30" }, "at": ["end"] },
    { "id": "audit",     "probe": "provenance_complete",  "args": { "matcher": "valentine party", "root": "isabella" }, "at": ["end"] }
  ],

  "pass": [                                  // predicates over the probe series (shape, not absolute)
    { "probe": "diffusion", "assert": "monotonic_nondecreasing" },
    { "probe": "diffusion", "assert": "min_final", "value": 0.33 },
    { "probe": "audit",     "assert": "==",        "value": 1.0 },   // 100% provenance-traceable
    { "probe": "intended",  "assert": "min_final", "value": 0.25 }
  ],

  "ablations": [                             // config deltas; same harness, branched via git
    { "id": "no_plan",      "dream": { "planner": false } },
    { "id": "no_reflect",   "dream": { "reflector": false } },
    { "id": "no_reconcile", "dream": { "reconciler": false } }
  ]
}
```

A new experiment = a new manifest. Diffusion/relationship experiments are the *same* schema
with different `seed`/`probes`/`pass`; they reuse every verb and probe.

## 4. Reusable interfaces (the only contracts to keep stable)

**Probe** — a pure read over the store, returns a value + audit detail; never mutates:
```
probe(world, store, args) -> { value: number, detail?: any, audit?: any }
```
Starter library (each is a thin query over `/memory/select`, `/memory/units`,
`/memory/timeline`, or the index): `knows`, `diffusion`, `relationship_density`,
`active_plan_fraction`, `provenance_complete` (walks `asserted_by`/`source_events`/
`derived_from` back to a root), `unit_count`, `stale_fraction`, `recall_agreement` (store vs
an LLM "interview"). New metric ⇒ one new probe, instantly reusable.

**Verb** — a host action that composes endpoints; the unit of stimulus:
```
verb(world, ctx, args) -> void    // performs action/dialogue (host) + observe (kernel)
```
Starter set: `converse` (recall both → host speaks → relay-observe into listener with
provenance), `relay`, `invite`, `sleep` (`/memory/dream`, deep/now), `announce_change`
(observe a correction so reconcile supersedes), `wait`. New interaction ⇒ one new verb.

**World adapter** — supplies agents, the clock, and the verb implementations:
```
adapter = { agents(), now(), step(), verbs:{...}, commit() }
```
`mud` drives a live host (LLM dialogue + action). `headless` fires scripted stimuli with no
dialogue LLM — for deterministic **kernel-correctness** experiments (reconcile/contradiction/
temporal/stale) that need no believable prose. Same manifest, same runner, different world.

## 5. The Runner (generic, experiment-blind)

```
load manifest + adapter + fixtures
seed()                                   # apply declarative seed ops
for t in clock(start..until, step):
    fire stimuli whose `at` == t         # via verbs
    fire due sleeps                      # dream(now=t, deep=cadence)  (ablation deltas applied here)
    if t is a checkpoint: sample probes(store) -> series
    adapter.commit()                     # git: per-tick replay point
evaluate pass(series) -> bool
for each ablation: restore(seed_ref); apply dream-delta; rerun; record series
report = { experiment, conditions: {full, ...ablations}, series, pass, audit }
```

The runner references nothing about diffusion or parties — it only executes hooks and samples
probes. Every experiment shares it.

## 6. Determinism, replay, ablation

- **Replay:** the per-tick commits make any run reproducible from any point; counterfactuals
  ("what if Isabella never told Maria?") are a `restore` + a schedule edit.
- **Ablation as a delta, not a fork:** toggles map to `dream(reflector=None|planner=None|
  reconciler=None)` — the exact knobs the kernel already exposes. Branch from the shared seed
  restore point; **diff** the probe series (no re-eyeballing). This reproduces the paper's
  core ablation finding, sharper.
- **Determinism budget:** the kernel is deterministic given inputs; the variance is the host
  LLM. Fix temperature/seed; or run on the `headless` adapter when the experiment doesn't need
  dialogue. Report absolute numbers as **reference bands**, assert on **shape** (monotonic,
  fraction, provenance==1.0) — model-independent.

## 7. Reporting & comparison

A run emits structured JSON: `{ experiment, condition, series:{probe:[(t,value)…]}, pass,
audit }`. The compare step renders the **ablation matrix** (full vs each delta), the **vs-paper
band**, and the **provenance audit** (did emergence earn its keep). Results are themselves
committable, so eval history is versioned alongside the memory it measured.

## 8. What the framework must already support (generality check)

The abstraction is not MUD-specific; it must express, with only manifests + probes + the right
adapter:

| Experiment family | adapter | seed / stimulus | key probes |
| --- | --- | --- | --- |
| Social emergence (the 3) | mud | conversations, invites, a time-change | diffusion, density, active-plan, provenance |
| Memory correctness | headless | inject a fact, later a contradicting/updated fact | reconcile-resolved?, stale-propagated?, valid-time correct? |
| Retrieval quality | headless | a corpus + labelled queries | recall@k, hybrid-vs-keyword, recall_agreement |
| Longitudinal identity | mud/headless | long run with persona + self-reflection | cornerstone stability, pinned-profile drift, belief churn |
| Scaling / cost | either | N agents × T ticks | tokens/agent, units/agent, dream latency, store size |

Each is the *same* runner. If a family needs a genuinely new measurement or action, it adds
one probe or one verb — additive, isolated, and reusable by every later experiment.

## 9. Staging

- **MVP:** the `headless` adapter + the starter probe/verb library + the runner, expressed in
  `examples/eval/` (HTTP-only, against `serve`). First manifests: the memory-correctness family
  (deterministic, no dialogue LLM — proves the harness end-to-end cheaply) and **Experiment C**
  from the emergence spec on a 5-agent `mud` adapter.
- **Full:** the `mud` adapter at 25 agents / 2 days; all three emergence manifests + the
  ablation matrix; a compare/report renderer; versioned eval history.
- **Deferred:** a web dashboard over runs; importance/recency-retrieval A/B (the two paper
  features we lack) as competing probes; auto-discovered manifest registry with a CLI
  `aigg-eval run <id> [--ablation X] [--seed N]`.

## 10. Non-goals

- **Not in the kernel.** The harness ships as a separate `examples/eval/` layer using only the
  public HTTP/CLI surface; the kernel gains no eval code and no new dependency.
- **Not a benchmark of prose quality** — that's the host LLM's; the harness tests the memory
  substrate (does the right fact/relationship/intention exist, resurface, and stay correct).
- **Not a world engine** — world, action, and dialogue belong to the world adapter / host.

## 11. The one-line contract

> A new experiment is a **manifest**: declarative seed + a sim-time stimulus schedule built
> from reusable **verbs** + read-only **probes** over the git-versioned store + shape-based
> pass predicates + config-delta ablations. The **runner**, **probe library**, **verbs**, and
> **adapters** are shared and stable. Adding the N-th experiment adds data, not machinery —
> and at worst one new probe or verb that every later experiment can reuse.
