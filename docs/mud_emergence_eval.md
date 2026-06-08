# mud.ai.gg — emergence evaluation spec

> Validate the three emergent social behaviors of Stanford *Generative Agents*
> (arXiv:2304.03442 — **information diffusion**, **relationship formation**,
> **coordination**) using aigg-memory as the memory substrate of a live MUD. This is the
> behavioral evaluation the architecture comparison flagged as the project's biggest "not
> yet": we built the substrate (observe → dream → reflect → plan → recall), but never
> measured whether it produces believable, emergent agent society. mud.ai.gg is our
> Smallville. Status: design. Date: 2026-06-07.

## 1. Goal & claim under test

The paper's headline result is *empirical*: a memory architecture (memory stream +
retrieval + reflection + planning) makes 25 agents, run for 2 game-days with no top-down
scripting, spontaneously **spread news**, **form relationships**, and **coordinate an
event** (Isabella's Valentine's Day party). The paper measured each.

**Claim under test:** aigg-memory's primitives are sufficient to reproduce all three
emergences when an LLM-driven MUD host owns the world, dialogue, and action. Concretely,
each emergence must arise from *only* these kernel operations — `observe`, `dream`
(consolidate + reconcile + reflect + plan), `recall` (`select` / `as_of`) — with **no
emergence hard-coded** in the host.

A second, stronger claim aigg-memory can test that the paper could not: every emergent fact
is **auditable** — diffused information carries provenance back to its source, relationships
rest on real encounters, and attendance rests on a plan with a valid rationale. The store is
inspectable typed markdown + a queryable index, so we measure emergence **directly from the
corpora**, not via the paper's noisy LLM-interview proxy.

## 2. Responsibility split (the action boundary, restated)

| Owner | Owns |
| --- | --- |
| **MUD host** (mud.ai.gg) | the world + clock (`now`), agents' bodies/locations, **action** (move, use objects), **dialogue generation** (the LLM that speaks), the tick scheduler, enacting plans, the experiment harness |
| **aigg-memory** (per-NPC) | each NPC's memory + cognition: `observe` (record), `dream` (consolidate/reconcile/reflect/plan), `recall` (inject), the typed graph, valid-time, provenance |

The kernel never acts. It records what happened, synthesizes beliefs/plans, and answers
recall; the host turns a recalled plan into an invitation, a recalled fact into a line of
dialogue. Consequences flow back as observations: **`recall → host acts/speaks → observe`**.

## 3. Substrate: one NPC

- **Corpus**: `npcs/<id>/memory` (isolated — memories never cross NPCs except through
  dialogue the host relays). **Evidence**: `npcs/<id>/evidence.jsonl`.
- **Identity**: a `pinned` self-profile unit (name, role, disposition) and a `locked`
  persona card the auto-loop never rewrites (per the persona guards). Optional `kind=goal`
  units (e.g. Isabella's `goal_host_party`) — durable, owner/author-set, `locked`.
- **Clock**: the host passes `now` (ISO sim-time) into every `dream`/`plan`/temporal call;
  the kernel ships no clock.
- **Kinds in play**: `episodic` (an encounter / a thing heard), `semantic` (a durable fact,
  e.g. "the party is at Hobbs Cafe, Feb 14, 5pm"), `belief` (reflection, e.g. "Maria likes
  Klaus"), `goal` / `plan` (intentions), `procedural` (skills, mostly unused here).

## 4. The two loops

**Online tick (per interaction, host-driven):**
```
1. recall      POST /memory/select   {corpus, request: <situation>, retriever:"hybrid", include_deps:true}
                                      -> bundle injected into the NPC's dialogue prompt
2. (host LLM generates the line / action — host's job)
3. observe     POST /memory/observe  {evidence, payload:{kind, slug, name, description, match, body,
                                      asserted_by:<speaker id>, ...}}     # for BOTH participants
```
When A tells B something, the host writes an observation into **B's** evidence stamped
`asserted_by: A` and `source_events:[<utterance id>]` — provenance for the audit.

**Offline sleep (per NPC, on its own trigger — scene end / nightly):**
```
POST /memory/dream  {evidence, corpus, write:true, deep:<periodic>, now:<sim-time>,
                     backend:"claude-cli"|"http", min_count:1}
   light: consolidate new evidence -> units; reconcile (a changed fact supersedes the old)
   deep : + compact + curate + reflect (facts->beliefs) + plan (goals+beliefs->intentions)
```
`consolidation-status` is the cheap readiness signal; the host owns when to fire sleep.

## 5. Experiment A — Information diffusion

**Seed.** One NPC (Isabella) holds a fact unit `event_valentine_party` ("Valentine's party
at Hobbs Cafe, Feb 14, 5pm"), `asserted_by: isabella`. No other NPC has it (t₀: 1/N know).

**Mechanism (kernel only).** During a conversation where Isabella's `recall` surfaces the
party fact, the host speaks it; the host then `observe`s it into the listener's evidence
(`asserted_by: isabella`, `source_events:[utterance]`). The listener's next `dream`
consolidates it into a unit. Later, the listener's own `recall` resurfaces it and the cycle
repeats to third parties. Diffusion is nothing but **observe → consolidate → recall**
chaining through the social graph; the kernel adds nothing bespoke.

**Metric (measured directly from the stores).**
```
knows(id, t)  := /memory/select on npcs/<id>/memory for "valentine party" returns the fact,
                 OR the index has a unit with match-term "party"/slug event_valentine_party
diffusion(t)  := |{id : knows(id,t)}| / N
```
**Audit (beyond the paper).** Walk each knower's unit `source_events`/`asserted_by` back to
Isabella: every "know" must have a provenance chain through real relayed utterances. A
knower with no chain = a host hallucination, and is a **failure** (the paper could not catch
this; we can — it ties to the "uncertain → defer, never guess" stance).

**Reference (paper, approx.):** party awareness 1/25 → ~12/25 over 2 days; Sam's candidacy
1/25 → ~8/25. **Pass:** diffusion(t) rises monotonically to a non-trivial fraction (target
≥ ⅓ of agents who had a conversational path to a knower), with **100% of knows
provenance-traceable** to the seed.

## 6. Experiment B — Relationship formation

**Seed.** Sparse initial acquaintance (the few "knows" the personas declare). Compute t₀
density.

**Mechanism (kernel only).** Each encounter, the host `observe`s an episodic "met <other>
at <place>, talked about <topic>" into **both** NPCs. `dream` consolidates per-acquaintance
into a `person_<other>` semantic unit; **reconcile** updates it as the tie deepens
(acquaintance → friend, or a correction if a first impression was wrong); the deep pass
**reflect**s relationship `belief`s ("Klaus respects Maria") `derived_from` the encounter
facts.

**Metric (directly from stores).**
```
edge(A,B,t) := npcs/A/memory has an active person_B unit (or a belief about B)
density(t)  := |edges| / (N*(N-1))
```
**Audit.** Every relationship belief's `derived_from` must point at real encounter units
(no invented history) — the same slug-validation reflect already enforces.

**Reference (paper, approx.):** network density ~0.167 → ~0.74 over 2 days. **Pass:**
density rises monotonically; every relationship `belief` has a valid, non-empty
`derived_from`; reconcile correctly supersedes stale impressions when a later encounter
contradicts an earlier one (a correctness check the paper's append-only stream had no way to
perform).

## 7. Experiment C — Coordination (the party) + replanning

This is the integrative test and the one where aigg-memory does work the paper only
approximated.

**Setup.** Isabella has `goal_host_party` (`kind=goal`, `locked`) and, after observing lonely
neighbors, a reflected `belief_neighbors_disconnected`. Her deep `dream`'s `plan()`
synthesizes `plan_host_valentines` (`kind=plan`, `valid_from = Feb14T17:00`,
`derived_from=[goal_host_party, belief_neighbors_disconnected]`, `apply:"invite guests,
decorate Hobbs Cafe"`).

**Enactment (host reads plan, acts).** The host `recall`s Isabella's plan (`select` /
`as_of(now, kinds=["plan"])`) and turns it into invitation **actions**. Each invite is
`observe`d into the guest's evidence ("Isabella invited me to the party, Hobbs Cafe, Feb 14
5pm"). The guest's `dream` may form `plan_attend_party` (`valid_from=Feb14T17:00`,
`derived_from=[invite_fact, goal_socialize?]`).

**Show-up (host queries intentions at party time).**
```
for each guest:  POST /memory/timeline or as_of("Feb14T17:00", kinds=["plan"])
                 -> has an active attend-party plan?  host moves them to Hobbs.
```
Attendance is a **subset** of knowers — guests with competing plans, or who didn't sleep in
time to form the intention, don't show. That gap is *believable* and, here, *explainable*
from the store.

**Replanning sub-experiment (our value-add).** Mid-run, Isabella moves the party to 5:30.
She `observe`s the change; her `dream`'s **reconcile** supersedes the old `event` fact
(temporal change, `valid_to`/`valid_from` stamped). Re-relayed to guests, each guest's
reconcile supersedes their old invite fact → **stale-propagation flags every dependent
`plan_attend_party` `stale`** across all guests with zero bespoke code (the
`mark_stale_dependents` blast-radius). Each guest's next `dream` re-`plan`s to the new time.
**Metric:** fraction of attend-plans correctly re-pointed to `valid_from=Feb14T17:30`; any
guest who shows at 5:00 (the stale time) is a stale-not-yet-replanned no-show — *traceable*,
not random. The paper's agents had no principled invalidation for a changed event; ours does.

**Metrics.**
```
invited / knew(among invited) / intended (active attend-plan at party time) / showed (host brought)
```
**Reference (paper, approx.):** ~12 knew/invited, **5 showed**. **Pass:** a non-trivial
subset forms intentions and shows; **every no-show has a store-traceable reason** (competing
plan, late sleep, stale plan); after the time change, ≥ most live attend-plans re-point to
the new time within one dream cycle.

## 8. Ablation — reproduce the paper's core finding on our substrate

The paper's main quantitative result was an **ablation**: removing reflection / planning
degrades believability. We reproduce it by toggling kernel steps and re-running the *same
seed* (git makes this exact):

| Condition | How | Expected effect |
| --- | --- | --- |
| full | dream with reconciler+curator+reflector+planner | all three emergences |
| no-plan | `dream(..., planner=None)` | Experiment C collapses — no attend intentions form; attendance ≈ 0 |
| no-reflect | `dream(..., reflector=None)` | relationships stay shallow (no "friend/rival" beliefs); coordination weaker (Isabella's `belief_neighbors_disconnected` never forms, so the party plan's rationale is thinner) |
| no-reconcile | `dream(..., reconciler=None)` | the replanning sub-experiment fails — guests keep the stale time; show-up at the wrong hour |

Because the corpora are git-versioned, each condition is a branch from the same `restore`
point; outcomes are **diffed**, not re-eyeballed. This is a sharper ablation than the paper's
(deterministic replay + direct store metrics).

## 9. Instrumentation & reproducibility

- **Direct measurement.** Every metric above is a query over the corpora (`/memory/select`,
  `/memory/units`, `/memory/timeline`, index reads) — no LLM interview needed. Optionally
  cross-check: run the paper's "interview" (a `recall` + a host-LLM yes/no) and assert it
  agrees with the store. Disagreement = a recall/believability gap worth logging.
- **Provenance audit.** Diffusion, relationship, and attendance claims are validated by
  walking `asserted_by` / `source_events` / `derived_from` — the emergence must be *earned*,
  not hallucinated.
- **Replay.** The host commits the world + each NPC corpus per tick (`/memory/commit` or git);
  `restore(ref)` re-runs from any point — for ablations, counterfactuals ("what if Isabella
  never told Maria?"), and debugging. Determinism: fix the host-LLM temperature/seed; the
  kernel is deterministic given its inputs.
- **Scale knobs.** Tick cadence, sleep cadence (`AIGG_MEMORY_DEEP_EVERY`), `min_count`,
  reflect/plan thresholds, backend (`claude-cli` for subscription auth, or an http model).

## 10. Staging

- **MVP (runnable, small-N):** extend `examples/mud-demo.mjs` to ~5 NPCs over 1 sim-day
  running **Experiment C** (the party) end-to-end against a live `serve`, with the diffusion
  and attendance metrics printed from the store. Proves the loop closes:
  observe → dream(reflect+plan) → recall → host enacts → observe. Include the time-change
  replanning step (the clearest aigg-memory-specific win).
- **Full:** 25 NPCs, 2 sim-days, all three experiments + the §8 ablation matrix, metrics
  logged per tick, compared against the paper's reference figures (as a sanity band, not a
  hard target — a different host LLM shifts absolute numbers; the *shape* must match:
  monotonic diffusion, rising density, a believable-and-traceable attendance subset).
- **Deferred:** hierarchical plan decomposition (day→hour→5-min, paper-style) for richer
  schedules; importance/recency retrieval signals (the two paper features we don't have) as
  an A/B against our repetition+curate approach; a web dashboard over the corpora.

## 11. Non-goals

- **Believable prose / persona voice** — that's the host LLM's job; this spec tests the
  memory substrate (does the right information/relationship/intention exist and resurface),
  not whether the dialogue reads well.
- **The world simulation, action, pathfinding, rendering** — the MUD host's job (the action
  boundary, §2).
- **Real-time performance / large-scale serving** — a separate concern; this is a
  correctness/emergence eval.

## 12. What a pass means

If all three emergences arise from only `observe`/`dream`/`recall`, with provenance-traceable
diffusion, rationale-backed relationships, and a believable-and-explainable attendance subset
that **correctly replans when the party time changes**, then aigg-memory is validated as a
sufficient memory substrate for believable multi-agent society — matching the paper's
architecture result *and* adding the memory-correctness guarantees (reconcile, valid-time,
provenance, no-guess) the paper's append-only stream lacked. That is the behavioral evidence
the kernel has so far been missing.
