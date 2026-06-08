# Planning — design spec

> The forward mirror of Reflection: from *beliefs + goals* to *intentions*. Status: **MVP
> implemented** (§8 MVP shipped — `kind=plan`/`goal`, the generative `plan()` op + future
> `valid_from`, replan via the existing stale-propagation, rationale recall, CLI/server/
> dream-deep wiring; §8 "Deferred" items remain open). Date: 2026-06-07. Reference
> architecture: Stanford *Generative Agents* (arXiv:2304.03442), whose ablation names three
> pillars — **observation**, **reflection**, **planning**. aigg-memory now has all three.
> **Action stays out of the kernel** (§6).

## 1. Motivation — Reflection looks back, Planning looks forward

[`reflection_design.md`](reflection_design.md) added the *backward* synthesis layer: read
accumulated facts and synthesize higher-level **beliefs** (`kind=belief`, `derived_from`
its evidence). Planning is the **forward** synthesis layer: read beliefs + goals and
synthesize **intentions** — what the agent means to do next ("the player is on a sword
quest *and* keeps losing → plan: offer a graded training arc starting tomorrow").

The two are mirror images over the *same* graph and the *same* LLM-synthesis machinery,
differing only in time direction:

| | Reflection (built) | Planning (this spec) |
| --- | --- | --- |
| direction | **backward**: facts → beliefs | **forward**: beliefs + goals → intentions |
| time | past / tenseless | **future** valid-time |
| unit | `kind=belief` | `kind=plan` |
| `derived_from` | the evidence it generalizes | the **rationale** it rests on (beliefs / goals) |
| invalidation | a changed fact makes the belief `stale` | a changed belief/goal makes the plan `stale` → **replan** |

The headline: planning is **almost no new machinery**. It reuses the graph, the
`derived_from` edge, the stale-propagation we built for reflection, and the valid-time
extension points (`valid_from`/`valid_to`/`precedes`/`timeline`/`as_of`). The only genuinely
new piece is the generative `plan()` op and a `kind=plan` unit with a *future* `valid_from`.

## 2. The MemoryMakefile *is* the planning substrate too

A plan's provenance — "I intend X *because of* beliefs B and goal G" — is the same directed
`derived_from` edge a belief uses, just pointing at a different layer (a plan points *down*
at the beliefs/goals that justify it). So **a plan tree is another subgraph of the
MemoryMakefile**, no new edge type. The graph does the same triple duty:

| direction | reflection use | planning use |
| --- | --- | --- |
| bottom-up | cluster facts to reflect on | **pick goals + relevant beliefs to plan toward** |
| the nodes | belief nodes + `derived_from` | **plan nodes + `derived_from` (rationale); `precedes` orders sub-steps** |
| top-down | `supports` blast radius → mark beliefs `stale` | **same `supports` walk → mark *plans* `stale` → replan** |

The third row is the key reuse and it is **already implemented**: `mark_stale_dependents`
walks `derived_from` reverse edges to *every* dependent — belief or plan alike. When
`reconcile`/`detect_contradictions` archives a fact, or a belief goes stale, any plan built
on it is flagged `stale` with **zero new invalidation code**. The paper's "reacting /
replanning" falls out of the blast-radius we already have.

## 3. Data model

- **`kind: plan`** — a new kind alongside `procedural | semantic | episodic | belief`. A plan
  is a future *intention*, not a recorded fact and not yet an action. Status is `candidate`
  by default (a **proposal**, needs an enact-decision — nothing acts on an unreviewed plan).
- **`derived_from: [slug, …]`** — already in the model: the plan's **rationale** (the beliefs
  and goals it rests on). Reverse query (`supports`) yields "which plans rest on this unit" —
  the replan blast radius. No schema change; `kind=plan` just uses the existing edge forward.
- **Future `valid_from` (+ optional `valid_to`)** — already indexed. A plan carries a
  *future* `valid_from` ("holds starting tomorrow"); `as_of(future_t)`/`timeline` answer
  "what is planned for time t" exactly as they answer "what was true at t" — the valid-time
  axis runs both ways. **New rule:** a plan's `valid_from` should be `>= now` (a plan is
  forward); a `valid_from` in the past is a degenerate/expired plan.
- **`precedes`** — already in the model: orders a plan's sub-steps ("step A precedes step B").
  Hierarchical decomposition (daily → hourly → minute, as in the paper) is plan-`precedes`-plan
  plus plan-`derived_from`-plan; MVP keeps a single plan unit with an ordered body and defers
  multi-level decomposition.
- **`stale: true`** — already the flag: set on a plan whose rationale changed; the plan stays
  usable but is queued for replanning. Same flag, same `mark_stale_dependents`.
- **`goal`** *(optional, may defer)* — a durable *desired end-state* the agent plans toward
  (the forward analog of a cornerstone belief). Owner- or agent-set, often `pinned`/`locked`
  (the auto-loop never rewrites it). MVP can fold goals into the beliefs/semantic units a plan
  `derives_from`; promoting `goal` to a first-class kind with its own management is deferred.
- **Authority**: a plan is the *agent's intention*, so like a belief it is **not** stamped a
  ground-truth `asserted_by`; `asserted_by = self`. `confidence` reflects how firm the plan is.

**Invariant — plan ≠ fact, and plan ≠ action.** A plan is a revisable proposal about the
future. `kind=plan` + `status=candidate` + `asserted_by=self` + future `valid_from` keep it
distinguishable from recorded facts (past) and from executed actions (which the kernel never
performs — §6). Facts and beliefs outrank plans when they conflict.

## 4. Operations

### 4.1 `plan` — the generative (forward) pass

```
memory.plan(root, corpus, planner, *, now, horizon=None, write=False,
            threshold=0.6, max_plans=8, goals=None, kinds=None, embedder=None) -> Dict
```

1. **Candidate selection (cheap, model-free).** Seed = the **goals** to plan toward
   (explicit `goals` slugs, or units tagged `kind=goal`, or — MVP fallback — the
   highest-salience active beliefs), plus their relevant belief/fact neighborhood (dependency
   + similarity). This differs from reflection's "cluster similar facts": planning is
   *goal-seeded*. Cap at `max_plans`.
2. **Synthesis (LLM).** `planner.plan(goals, context, now, horizon)` → new plans:
   `[{slug, name, description, body, valid_from, derived_from:[slug…], steps?, confidence}]`,
   where `derived_from` is the rationale (given slugs only) and `valid_from >= now`.
3. **Validate.** Every `derived_from` slug must be a real unit (no hallucinated rationale —
   exactly like reflect/infer-deps validate slugs). Drop a plan with no valid rationale.
   Clamp/reject a `valid_from < now`. A slug colliding with an existing (non-locked) plan →
   re-plan: merge rationale, clear `stale`.
4. **Write** (`write=True`): create `kind=plan` units, status `candidate`, `asserted_by=self`,
   with `derived_from` edges and the future `valid_from`, then `update_index`. Dry-run default.

Mirrors `reflect` (generative, produces units, slug-validated, dry-run). New:
`extract.AIGGPlanner` + `parse_plans` (tolerant; drop items without a name/`derived_from`/
`valid_from`). Backend-agnostic (http / claude-cli), like the others.

### 4.2 Replanning — already built

```
memory.mark_stale_dependents(root, corpus, changed_slugs)   # already implemented for beliefs
```

No new code. The existing stale-propagation walks `derived_from` reverse edges to **any**
dependent, so a plan resting on a fact/belief that `reconcile`/`detect_contradictions` archives
(or that itself goes stale) is flagged `stale` automatically and surfaced in those results'
`stale_marked`. A later `plan` pass regenerates the stale plans. The app owns the
*decision* to replan/react on that signal (§5) — the kernel only flags.

### 4.3 Recall — plans ↔ rationale, and "what's planned for t"

`dependency_closure` already follows `derived_from`, so recalling a **plan** pulls its
rationale (the beliefs/goals behind it) for free — the same generalization belief recall got.
`as_of(future_t)` / `timeline(kinds=["plan"])` answer "what is planned for time t" using the
valid-time index that already exists. An agent's recall bundle becomes: what it knows
(facts), what it believes (beliefs), **and what it intends (plans)**.

## 5. Lifecycle, trigger, horizon, identity

- **Where it sits:** `observe → DREAM (consolidate + reconcile + curate) → REFLECT → PLAN`.
  Plan runs in **Dream's deep pass, right after reflect**, so it plans off freshly-updated
  beliefs — already on the periodic, app-owned cadence. It needs a model (like
  reconcile/curate/reflect) and the caller's `now` (the kernel ships no clock, exactly as
  `reconcile` takes `now`); skipped when no model is configured.
- **Trigger (app policy, no engine scheduler):** plan when goals/beliefs changed materially,
  or at a horizon boundary (start of day/scene). MVP: piggyback the deep-pass cadence + the
  `stale`-plan signal as the replan cue; a dedicated horizon scheduler is deferred.
- **Goals / identity:** durable goals are the forward cornerstone — the load-bearing
  "what this agent is trying to do." Owner-set goals are `locked` (never auto-rewritten, per
  the persona-card guards); high-salience self-goals may be proposed for the pinned profile,
  owner-gated — the same identity feedback loop reflection has, pointed forward.

## 6. Safety boundaries — Action is NOT in the kernel

This is the line the spec exists to draw. aigg-memory is a **memory kernel, not an agent
runtime**: no clock, no scheduler, no executor. The paper's third pillar (planning) lands
*inside* the kernel as a memory artifact (a plan is a retrievable, reflectable unit); the
**act of doing** stays *outside*, in the host loop (a MUD, an orchestrator, Claude Code).

- **Plan ≠ action.** The kernel stores intentions and flags them; it never executes one. A
  plan is `status=candidate` precisely so nothing auto-acts on an unreviewed proposal.
- **The loop closes through observations.** The app enacts a plan and the *consequences* come
  back as episodic observations (`observe`), which the next Dream consolidates and the next
  Reflect/Plan learns from — `observe → reflect → plan → (app acts) → observe`. The kernel
  owns every arrow except the parenthesized one.
- **Why the boundary holds (safety):** a memory store that could trigger actions is a
  categorically more dangerous component. Keeping execution in the host preserves the
  least-privilege, auditable, git-versioned nature of the store and matches the project's
  "the app owns triggers" stance (the engine already ships no scheduler).
- **Plan != commitment:** reconcile / contradiction / curate apply to plans too — a plan
  contradicted by a new belief is superseded; stale plans are re-planned or pruned. Plans are
  *more* revisable than facts, by design.
- **Protected nodes:** `locked` goals and `pinned` plans are never auto-archived or rewritten
  (existing guards apply unchanged — plans are just units).
- **No hallucinated rationale:** every `derived_from` is validated against real slugs, and a
  plan's `valid_from` must be `>= now` (no back-dating a future intention).

## 7. API surface

- `extract.AIGGPlanner` + `parse_plans` (backend-agnostic, token-budget headers).
- `memory.plan(...)`; **reuses** `mark_stale_dependents` (replan), `dependency_closure`
  (rationale recall), `timeline`/`as_of` (what's planned). `kind=plan` (+ optional `goal`)
  added to `VALID_KINDS`. No new edge type; no new index column.
- CLI: `plan` (mirrors `reflect`/`reconcile` flags incl. `--backend`, plus `--now`/`--horizon`);
  recall already surfaces a plan's rationale via `--include-deps`.
- Server: `POST /memory/plan`; `/memory/dream` deep pass includes it (after reflect).
- Plugin / MUD: the deep Dream already runs on `AIGG_MEMORY_DEEP_EVERY`; plan rides it. For a
  MUD, an NPC's plans are its evolving intentions toward the player/world; the game loop reads
  them (recall / `as_of`), **acts**, and feeds outcomes back as observations.

## 8. Staging

- **MVP:** `kind=plan` (+ optional `goal` tag); `AIGGPlanner` + `plan` (generative,
  rationale-validated, future-`valid_from`, dry-run default); replan = **reuse** the existing
  stale-propagation (no new code); recall pulls a plan's rationale; plan rides Dream's deep
  pass after reflect; CLI + server + dream wiring; tests.
- **Deferred:** first-class `goal` kind + goal management; hierarchical plan decomposition
  (daily → hourly → minute via plan-`precedes`-plan + plan-`derived_from`-plan); a dedicated
  horizon/importance planning trigger; plan-outcome feedback (link an enacted plan to its
  episodic result, then reflect on "did it work?"); temporal "how my plan for X evolved".
- **Non-goal (permanently out of kernel):** executing actions, side effects, tool calls, a
  scheduler/clock. Those belong to the host agent loop.

## 9. Test plan (TDD)

- `plan`: synthesizes a plan from a goal + beliefs; `derived_from` (rationale) validated
  (hallucinated source dropped); `valid_from >= now` enforced; writes `kind=plan`, status
  `candidate`, `asserted_by=self`, with edges; dry-run no-writes.
- graph: a plan's `derived_from` compiles into the dependency graph; `supports` reverse query
  finds the plan from its rationale; plan recall pulls the rationale; doesn't pollute
  `depends_on`.
- replan: reconcile/contradiction archiving a fact (or a belief going stale) marks the
  dependent **plan** `stale` via the *existing* `mark_stale_dependents` — assert no new code
  path is needed; a re-plan clears the flag.
- temporal: `as_of(future_t, kinds=["plan"])` / `timeline(kinds=["plan"])` surface a plan at
  its future `valid_from`.
- guards: a `locked` goal / `pinned` plan is never auto-rewritten; a plan is not stamped a
  fact `asserted_by`; the kernel performs no action (only records/flags).
- backend: plan works over http and claude-cli (stubbed), like reflect/reconcile.

## 10. Decisions (settled 2026-06-07 — leans adopted)

1. **Kind names:** `plan` (chosen). `goal` **is recognized as a kind** (added to `VALID_KINDS`,
   usable as a planning seed) but first-class *goal management* is deferred — MVP seeds from
   `kind=goal` units when present, else falls back to active beliefs. **Implemented.**
2. **Plan status: `candidate`** — a proposal needing an enact-decision; nothing auto-acts on it
   (keeps the action boundary crisp). **Implemented.**
3. **Where plan runs:** rides Dream's deep pass **after reflect** (one cadence, fresh beliefs);
   the caller supplies `now`. A dedicated horizon scheduler stays deferred. **Implemented.**
4. **Sub-step representation:** single plan unit with an ordered body (MVP). Hierarchical
   plan-`precedes`-plan decomposition remains deferred. **Implemented (MVP form).**
5. **Replan policy:** the kernel only *flags* `stale` (via the existing `mark_stale_dependents`,
   reused unchanged); the **app** decides to react/replan and to act. **Confirmed.**
