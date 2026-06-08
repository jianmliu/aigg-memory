# mud.ai.gg — the configurable agent sandbox

> mud.ai.gg is not a game; it is a **sandbox** that provides reusable **rails** (world
> mechanics + safety boundaries) and runs **experiments by configuration, not code**. It is
> the `mud` world adapter of [`experiment_harness.md`](experiment_harness.md), one level above
> the harness's generic runner and below the specific experiment manifests. Status: design.
> Date: 2026-06-08.

## 1. One sandbox, two roles

The same sandbox is both the **product** (a live agent-MUD where NPCs carry real
aigg-memory) and the **lab** (a configurable rig for behavioral experiments). They differ
only by configuration:

| | Product (live) | Lab (eval) |
| --- | --- | --- |
| dialogue / action | a real host LLM speaks & acts | scripted / stub (deterministic) |
| schedule | open-ended player-driven | a fixed stimulus schedule |
| measurement | none / analytics | probes over the store + pass predicates |

**You validate the very system you ship, in the same sandbox** — the emergence eval
([`mud_emergence_eval.md`](mud_emergence_eval.md)) is just the product running in lab mode.
The rails are constant; only the config changes.

## 2. "Rail" has two senses — both are the design

- **Affordance-rails — the tracks agents run *on*.** The fixed, reusable set of things that
  *can* happen (move, meet, converse, relay, invite, sleep, recall). Experiments compose
  these; they never reimplement world mechanics.
- **Guard-rails — the limits agents run *within*.** The boundaries that *can't* be crossed:
  the kernel never acts, every relayed fact carries provenance, agents act only through
  sandboxed affordances (no arbitrary tool use), runs are seedable/auditable.

A sandbox is exactly "a bounded space of safe affordances." mud provides both rails so an
experiment is a *configuration over a safe, fixed vocabulary*, not free-form code.

## 3. The rails library

| rail group | provides | binds to aigg-memory |
| --- | --- | --- |
| **World** | places (a spatial graph), objects, co-location/presence | sets the *context* string for `recall` |
| **Time** | sim-calendar, tick scheduler, sleep/wake cadence | supplies `now` to `dream`/`plan`; drives sleep |
| **Social** | encounter, **converse** (a dialogue turn), **relay** (info passing), invite, gift, host/attend an event | each turn → `observe` into both parties (with provenance) |
| **Memory** | the standardized per-NPC loop: perceive→`observe`, sleep→`dream` (consolidate/reconcile/reflect/plan), act→`recall`-into-prompt | one corpus per NPC (`npcs/<id>/memory`) |
| **Safety** | the action boundary, provenance stamping, sandboxed affordance set, determinism/seed | `asserted_by`/`source_events`; `needs_review` surfaced, never guessed |
| **Instrumentation** | every world event logged + git-committed per tick | the store *is* the measurement substrate; probes read it |

The Social and Memory rails are the `verbs` the harness already names (`converse`, `relay`,
`invite`, `sleep`); mud adds the World and Time rails (places, calendar) that a headless run
doesn't need. A new mechanic = one new rail, reusable by every later experiment — the same
additive rule the probe/verb libraries follow.

## 4. Experiments by configuration

An experiment is a layered config (the harness manifest, enriched with world/cast):

```jsonc
{
  "world":  { "adapter": "mud",
              "places": "fixtures/smallville/places.json",     // World rail config
              "clock":  { "start": "...", "step": "PT1H", "until": "..." } },
  "cast":   { "agents": "fixtures/smallville/agents/", "n": 25 },// personas + initial corpora
  "scenario": {
     "seed":     [ /* declarative initial facts/goals */ ],
     "schedule": [ /* sim-time-keyed rail firings: converse, invite, announce_change */ ],
     "perturbations": [ /* e.g. move the party time — exercises reconcile + replan */ ]
  },
  "cognition": { "dream": ["consolidate","reconcile","reflect","plan"],  // which steps run
                 "cadence": "AIGG_MEMORY_DEEP_EVERY", "backend": "stub|http|claude-cli",
                 "ablations": [ {"id":"no_plan","off":["plan"]} ] },     // toggles, not forks
  "measure":  { "probes": [...], "pass": [...] }                          // read-only over the store
}
```

Every axis is data: cast size, which rails fire and when, which cognition steps are on, what
to measure. **No code per experiment.** The result is an *experiment matrix* for free —
ablation × cast-size × perturbation × persona — all configuration.

## 5. mud as the harness's `mud` adapter

mud realizes the `World adapter` contract (`agents() / now() / step() / verbs / commit()`):
it supplies the agents, the clock, the rail implementations, and per-tick git commits. The
**dialogue fidelity is itself a config knob** (`cognition.backend`): a real host LLM for the
live product, or a scripted/stub model for deterministic eval — mirroring the headless/mud
split, with the rails unchanged. So the MVP eval harness (`examples/eval/`, headless) and the
full mud sandbox are the *same runner* at two fidelities.

## 6. The matrix you get for free

Because everything is config + rails + git replay:

- **Ablation** (the paper's method): `cognition.ablations` toggles dream steps; branch from a
  shared seed, diff the probe series.
- **Dose-response**: sweep `cast.n` or cadence; watch diffusion/coordination scale.
- **Counterfactual**: `restore(ref)` + edit one schedule entry ("what if Isabella never told
  Maria?") — replay diverges from a known point.
- **Persona A/B**: swap the cast fixtures; same scenario, different agents.

## 7. Guardrails, restated (the safety the sandbox enforces)

- **The kernel never acts.** All action flows through sandboxed affordance-rails owned by the
  host; aigg-memory only records, synthesizes, and answers recall.
- **Provenance on every relay.** A `converse`/`relay` rail stamps `asserted_by` +
  `source_events`, so diffusion/relationships/attendance are *auditable* — emergence must be
  earned, not hallucinated. `needs_review` is surfaced, never guessed.
- **Bounded affordance set.** Agents do only what the rails expose — no arbitrary tool use,
  no escape from the sandbox. (Mirrors the project's least-privilege stance.)
- **Deterministic & replayable.** Seed the stub/dialogue source; the kernel is deterministic
  given inputs; per-tick commits make any run reproducible and any counterfactual a `restore`.

## 8. Relationship to aigg-memory

mud is **outside** the kernel (the action boundary). It depends on aigg-memory only through
the public HTTP surface: one corpus per NPC, `observe` on perception, `dream` on the sleep
rail, `recall`/`as_of` into the dialogue prompt. The kernel gains nothing mud-specific; mud is
a host that happens to be configurable into a lab.

## 9. Staging

- **Rails MVP — shipped** in [`examples/eval/`](../examples/eval/): the `mud` adapter
  (one corpus per NPC) with the Social rails (`relay`/`invite`/`announce_change`), scripted
  dialogue (deterministic), and multi-corpus probes (`knows_count`/`plan_count`/
  `stale_plan_count`/`provenance_ok`). **Experiment C** (the party + the time-change
  perturbation) runs by *configuration* — diffusion, a believable intent subset, cross-NPC
  replanning via reconcile+stale, a provenance audit, and the `no_reconcile` ablation flip —
  all green. The **World (`move`/places) + Time (`tick`/`sleep`) rails** are in too
  (`mud_spacetime_party`): diffusion gated by co-location, attendance by place-at-time, the
  funnel `knew > intended > showed` emerging from physics. All three emergences pass.
- **Scale — shipped**: `examples/eval/smallville.py` generates a 25-agent / 12-tick run from
  compact config (seeded → replayable) and prints an **ablation matrix** — reproducing the
  paper's headline figures (diffusion 1/25 → ~12/25 ≈ 48%; network density rising; cut
  conversation → no diffusion, cut encounters → no network). Next: explicit World (places) +
  Time (calendar) configs, then live mode.
- **Full:** the 25-agent / 2-day Smallville config + the ablation matrix; then **live mode**
  (real host LLM) sharing the identical rails.
- **Deferred:** a config/authoring UI; a richer object/action ontology; multiplayer (real
  players alongside NPCs in the same sandbox).

## 10. Non-goals

- **Not a kernel feature.** The sandbox ships as a host/eval layer on the public surface; the
  kernel stays domain-agnostic and action-free.
- **Not a fixed scenario.** mud is the *space* of experiments (rails + config), not any one
  game or eval; Smallville is one configuration among many.
- **Not a world engine benchmark.** Rendering, pathfinding, real-time performance are the
  host's concern; this design is about the rails + configuration that make experiments cheap
  and the memory substrate testable.
