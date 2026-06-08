# Reflection — design spec

> The synthesis layer above Dream: from *facts* to *beliefs*. Status: **MVP implemented**
> (§8 MVP shipped — `kind=belief`, `derived_from` edges, `reflect`, stale-propagation,
> belief↔fact recall, CLI/server/dream-deep wiring; §8 "Deferred" items remain open).
> Date: 2026-06-07.

## 1. Motivation — Dream consolidates, Reflection synthesizes

aigg-memory today ends at **Dream**: the offline maintenance pass (consolidate evidence →
typed units, reconcile contradictions / temporal change, compact duplicates, curate noise).
Dream is **preservative** — it keeps the *facts* correct and compact; it never invents new
meaning.

**Reflection** is the layer above: read the accumulated memories and **generate new,
higher-level beliefs** that aren't present in any single fact ("the player visited five
times, always asking about swordsmanship after a loss → the player is on a quest to master
the sword, and is frustrated"). This is the engine of characterization / identity — in
Westworld terms, Dream is the host's nightly memory replay; **Reflection is the reverie**
that re-interprets accumulated experience and, over time, builds a self. The reference
architecture is Stanford's *Generative Agents* (observation → reflection tree → behavior).

| | Dream (built) | Reflection (this spec) |
| --- | --- | --- |
| operation | preserve / organize | **generate** new meaning |
| output | facts (same level) | **beliefs** (one level up) |
| nature | does not invent facts | **invents interpretations** (may be wrong, revisable) |

## 2. The MemoryMakefile *is* the reflection substrate

A reflection's provenance — "this belief was synthesized from facts X, Y, Z" — is a directed
edge between units, the same shape the MemoryMakefile already compiles (`deps` / `references`
/ `supersedes` / `precedes`). So **a reflection tree is a subgraph of the MemoryMakefile**
with one new edge type, `derived_from` (belief → its supporting units; reverse = `supports`).

The graph built for human navigation + dependency-aware recall does **triple duty** for
reflection:

| direction | existing use | reflection use |
| --- | --- | --- |
| bottom-up | cluster units by deps / similarity | **pick what to reflect on** (dense fact clusters / recent high-salience leaves) |
| the nodes | units + typed edges | **the reflection tree itself** (`belief` nodes + `derived_from` edges; recursive — a belief may derive from beliefs) |
| top-down | `depended_by` = blast radius | **invalidation**: when a fact is superseded, walk the reverse edges to find the beliefs built on it → mark `stale` → re-reflect |

The third row is the key reuse: the blast-radius we built for "what does editing this unit
touch" **is** "which beliefs must I reconsider when a fact changes." The MemoryMakefile is
the propagation medium between the consolidation layer (Dream) and the synthesis layer
(Reflect).

## 3. Data model

- **`kind: belief`** — a new kind alongside `procedural | semantic | episodic`. A belief is
  an *interpretation*, not a recorded fact. Consolidation status for beliefs is `candidate`
  by default (like procedural — needs-review), not auto-active.
- **`derived_from: [slug, …]`** — frontmatter list on a belief: the units it was synthesized
  from. Compiles into the dependency graph as `rel="derived_from"`; reverse query yields
  `supports` (which beliefs a fact underpins). Add `"derived_from": "derived_from"` to
  `_REL_FIELD`; add `"derived_from"` to the index `deps`-table rel set and to `sync`.
- **`stale: true`** — a frontmatter flag set on a belief whose supporting facts changed; it
  remains usable but is queued for re-reflection. (A flag, like `pinned`/`locked`, not a
  status — a stale belief is still `active`.)
- **Authority**: a belief is the *agent's inference*, so it is **not** stamped with a
  ground-truth `asserted_by`; instead `asserted_by` (if set) is the reflecting agent/self,
  and `confidence` defaults to `medium`/`low`. Beliefs carry `apply` like any unit (how to
  act on the belief).

**Invariant — belief ≠ fact.** Reflections must never be presented as recorded ground truth.
`kind=belief` + no fact-`asserted_by` + lower confidence keep them distinguishable, revisable,
and subordinate to facts when they conflict.

## 4. Operations

### 4.1 `reflect` — the generative pass

```
memory.reflect(root, corpus, reflector, *, write=False, threshold=0.6,
               max_clusters=8, kinds=None, embedder=None) -> Dict
```

1. **Candidate selection (cheap, model-free).** Pick clusters of related units to reflect
   on: dependency neighborhoods + `similar_pairs(threshold)` clusters, optionally limited to
   recent / high-confidence / specified `kinds` (default: non-belief units, so we reflect on
   facts first; recursive reflection includes beliefs). Cap at `max_clusters`.
2. **Synthesis (LLM).** `reflector.reflect(units)` → new beliefs:
   `[{slug, name, description, body, apply?, derived_from:[slug…], confidence}]`.
3. **Validate.** Every `derived_from` slug must be a real unit (no hallucinated sources);
   drop a belief with no valid sources. A belief slug colliding with an existing belief →
   treat as an update (supersede the prior belief, carrying its `derived_from`).
4. **Write** (`write=True`): create `kind=belief` units, status `candidate`, with the
   `derived_from` edges, then `update_index`. Dry-run by default.

Mirrors the `AIGGReconciler` / `AIGGCurator` shape, but **generative** (produces units)
rather than judging. New: `extract.AIGGReflector` + `parse_reflections` (tolerant; drop items
without a name/derived_from). Backend-agnostic (http / claude-cli), like the others.

### 4.2 Invalidation — stale propagation

```
memory.mark_stale_dependents(root, corpus, changed_slugs) -> [slug…]
```

When Dream's reconcile/contradiction archives or supersedes a unit, walk the index over
`derived_from` reverse edges (`depended_by`-style) from the changed slugs and set
`stale: true` on every belief that transitively derives from them. Called automatically at
the end of `reconcile`/`detect_contradictions` (when `write`) and surfaced in their result.
A later `reflect` pass regenerates the stale beliefs (re-synthesize, supersede the stale one).

### 4.3 Recall — beliefs ↔ supporting facts

Generalize `include_deps`: recalling a **belief** can pull its `derived_from` closure (the
supporting facts), and a flag pulls the reverse (recalling a **fact** surfaces the beliefs
built on it). One graph, both directions; reuse `dependency_closure` over the `derived_from`
rel. Beliefs participate in the kind-aware recall bundle (an agent recalls both what it knows
*and* what it believes).

## 5. Lifecycle, trigger, identity

- **Where it sits:** `observe → DREAM (consolidate + reconcile + curate) → REFLECT`. Reflect
  runs in **Dream's deep pass** (after compact + curate), so it's already on the periodic,
  app-owned cadence (`--deep`, `AIGG_MEMORY_DEEP_EVERY`). It needs a model (like
  reconcile/curate) — skipped when none is configured.
- **Trigger (app policy, no engine scheduler):** a readiness signal — reflect when enough
  new high-salience facts accrued since the last reflection (Generative-Agents-style
  importance threshold). MVP: piggyback the deep-pass cadence; a dedicated
  `reflection-status` signal is deferred.
- **Cornerstone / identity:** the most-`depended_by` beliefs (high centrality in the belief
  layer) are the load-bearing self-beliefs — the cornerstone. The existing graph centrality
  finds them; an owner-set cornerstone is `locked` (the auto-loop never rewrites it, per the
  persona-card guards). High-salience *self*-reflections may be proposed for the pinned
  profile — the cornerstone → identity feedback loop, owner-gated.

## 6. Safety boundaries

- **Belief ≠ fact** (§3 invariant): never surface a belief as asserted ground truth.
- **Beliefs are revisable:** reconcile / contradiction-detection apply to beliefs too — a
  belief contradicted by a new fact is superseded; curate prunes low-value beliefs. Beliefs
  are *more* subject to revision than facts, by design.
- **Protected nodes:** `locked` (owner cornerstone) and `pinned` beliefs are never auto-
  archived or rewritten (existing guards in reconcile/curate/contradiction/compaction apply
  unchanged — beliefs are just units).
- **No hallucinated sources:** every `derived_from` is validated against real slugs (no
  inventing evidence), exactly as `infer-deps`/`reconcile` validate their slugs.
- **Don't over-reflect:** cap clusters per pass; the candidate filter avoids re-reflecting
  unchanged regions; stale-propagation targets re-reflection at what actually changed.

## 7. API surface

- `extract.AIGGReflector` + `parse_reflections` (backend-agnostic, token-budget headers).
- `memory.reflect(...)`, `memory.mark_stale_dependents(...)`; `_REL_FIELD["derived_from"]`;
  index `derived_from` rel + `belief` kind; `stale` flag.
- CLI: `reflect` (mirrors `reconcile`/`curate` flags incl. `--backend`); recall gains a
  beliefs/supports option; `dream --deep` calls reflect.
- Server: `POST /memory/reflect`; `/memory/dream` deep pass includes it.
- Plugin: the deep Dream already runs on `AIGG_MEMORY_DEEP_EVERY`; reflect rides it. For a
  MUD, an NPC's reflections are its evolving beliefs about players/world.

## 8. Staging

- **MVP:** `kind=belief` + `derived_from` edge; `AIGGReflector` + `reflect` (generative,
  slug-validated, dry-run default); stale-propagation on reconcile/contradiction writes;
  recall pulls a belief's supporting facts; CLI + server + dream-deep wiring; tests.
- **Deferred:** importance-scored `reflection-status` trigger; auto-promotion of self-
  reflections into the pinned profile; recursive multi-level reflection tuning; temporal
  reflection ("how my belief about X changed over time" using `valid_from`/`precedes`).

## 9. Test plan (TDD)

- `reflect`: synthesizes a belief from a fact cluster; `derived_from` validated (hallucinated
  source dropped); writes `kind=belief`, status `candidate`, with edges; dry-run no-writes.
- graph: `derived_from` compiles into the dependency graph; `belief` recall pulls supporting
  facts; doesn't pollute `depends_on`.
- invalidation: reconcile archiving a fact marks its derived beliefs `stale`; a re-reflect
  supersedes the stale belief.
- guards: a `locked` belief is never auto-rewritten; a belief is not stamped with a fact
  `asserted_by`.
- backend: reflect works over http and claude-cli (stubbed), like reconcile/curate.

## 10. Decisions (settled 2026-06-07 — defaults accepted)

1. **Edge name:** `derived_from` (belief→facts), reverse `supports` — matches the `deps`
   direction (a unit points at what it needs). **Implemented.**
2. **`stale` is a flag, not a status:** a stale belief stays `candidate`/active + `stale: true`
   (graceful — still recalled until re-reflected, which clears the flag). **Implemented.**
3. **Recursive depth: uncapped.** Belief-on-belief is allowed (pass `kinds=["belief"]`); the
   graph handles cycles. A depth guard is deferred until noise warrants it.
4. **Self-reflection → profile promotion: manual.** High-centrality self-beliefs are pinned
   by the owner (`edit --pin`); auto-promotion stays deferred (don't auto-rewrite identity).

Also settled: belief `kind` name is `belief`; beliefs are stamped `asserted_by: self`
(provenance + the belief≠fact boundary); reflection rides Dream's deep pass (no dedicated
importance trigger yet); candidate selection is similarity-cluster based (non-belief by
default). Deferred items are tracked in §8.
