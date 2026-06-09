# aigg-memory: A Git-Versioned, Provenance-Carrying Memory Kernel with Mirror Reflection and Planning

**Status:** DRAFT skeleton — section stubs + claims + pointers to source. Fill prose where marked `‹TODO›`.
**Scope:** the *kernel* as a standalone systems/methods contribution. The economics (ELC / talent-vs-luck)
and the Stanford-Smallville emergence reproductions are a separate *applied* paper that cites this one
(see `docs/memory_economy_research.md`, `docs/mud_emergence_eval.md`).

**Source of truth (keep this draft in sync):**
kernel `src/aigg_memory/{memory,index,extract,server,agent}.py` ·
designs `docs/{reflection_design,planning_design,architecture}.md` ·
eval `examples/eval/README.md` · tests `tests/`.

---

## Abstract

‹TODO 150–200 words.› Draft: Agent memory is usually a vector store of opaque text. We present
**aigg-memory**, a memory kernel that instead represents memory as a **git-versioned, typed,
provenance-carrying dependency graph** of markdown units. Two synthesis operations — **reflection**
(backward: episodes → beliefs) and **planning** (forward: goals + beliefs → intentions) — are
*mirror images over the same graph*, and a single **stale-propagation** along provenance edges yields
both belief revision and replanning with no extra machinery. Decisions read a belief's **evidence**
(`derived_from`), not its surface text, making cognition **model-agnostic and robust to wording**.
The kernel runs on cheap local models (Ollama) as well as cloud models. We argue for a **two-tier
evaluation**: a deterministic stub validates architecture and math; a real (local) model validates
judgment quality and surfaces engineering gaps the stub cannot. ‹TODO headline numbers.›

---

## 1. Introduction

- **Problem.** LLM agents need durable memory, but the dominant pattern (embed text → top-k recall)
  loses *type*, *provenance*, *time*, and *causal structure*. Belief revision, replanning, and audit
  are then bolted on per-application.
- **Thesis.** Treat memory as a **typed, versioned, provenance graph** with a small set of operations,
  and these capabilities fall out of one substrate.
- **Contributions** (each maps to a section):
  1. A **bitemporal typed memory graph** — kinds, typed edges, provenance, valid-time over git (§4).
  2. **Mirror synthesis**: reflection and planning as backward/forward duals over the same graph, with
     **stale-propagation** giving belief-revision *and* replan from one mechanism (§5).
  3. **Provenance-based cognition**: decide by a belief's *evidence*, not its text → model-agnostic,
     wording-robust, no LLM/embedding at decision time (§6).
  4. **Model-agnostic extraction**: tolerant parsing, per-operation model routing, field coercion →
     works on cheap local models, not locked to one provider (§7).
  5. **Epistemic conservatism** as invariants: uncertain → defer, never guess; belief ≠ fact; plans
     never auto-act (§8).
  6. A **two-tier evaluation methodology** (stub vs. real-local-model) and the concrete engineering
     gaps it surfaced (§9).
- ‹TODO one paragraph: what we are *not* claiming (not SOTA retrieval; not a new LLM).›

## 2. Related work

‹TODO, grouped:›
- **Agent memory / generative agents.** Stanford Smallville (arXiv:2304.03442) memory-stream +
  reflection + planning; MemGPT; vector-store memory. Contrast: we type and version memory and make
  reflection/planning duals over an explicit graph.
- **Knowledge representation / truth maintenance.** TMS/ATMS, justification graphs — `derived_from` +
  stale-propagation is a lightweight, LLM-era TMS.
- **Bitemporal databases.** transaction-time (git) × valid-time (`valid_from/valid_to`).
- **Provenance / data lineage.** why-provenance ≈ our decide-by-evidence.
- **Skills / typed prompt artifacts.** the unit *is* a `SKILL.md`.

## 3. Design overview

**The substrate.** A corpus is a directory of units (`‹corpus›/‹slug›/SKILL.md`, §4) linked by typed
edges — a dependency graph we call a **MemoryMakefile**. Each agent (NPC, user, session) gets its own
corpus (`npcs/‹id›/memory`, …), so memory is per-entity and the same kernel serves one user or a town
of NPCs unchanged.

**The operations are pure functions over corpus snapshots.** Every kernel operation reads the corpus,
computes, and either returns a result or writes new units — it holds no session state, opens no socket
to the world, and embeds no clock. This is what makes the kernel testable (a deterministic stub yields
a deterministic result, §9) and embeddable (the host calls it in-process or over HTTP).

**The host/kernel boundary.** The kernel is a *cognition substrate*; it deliberately does **not** own
the three things that couple a system to the world:
- **Perception** — turning dialogue/events into observations is the host's job (it calls `observe` /
  `ingest`). The kernel ingests structure, it does not watch the world.
- **Action** — the kernel emits a `plan` (`status=candidate`); **enacting** it is the host's job. The
  kernel proposes, never acts.
- **Time** — *the kernel ships no clock.* Operations that need "now" (`plan`, `reconcile`, `timeline`)
  **require the host to pass `now`**. World-time is a host input, never an ambient global — which is
  precisely why valid-time queries are reproducible and tests are deterministic.

So a turn looks like: host perceives → writes via `observe`/`remember`/`ingest`; periodically the host
runs the **offline pass** (consolidate → reconcile → reflect → plan, the "Dream"); host reads via
`select` and **enacts** the candidate plans. Three hosts exercise the same API: a **MUD** (per-NPC
memory + nightly dream), an **inference gateway / Claude plugin** (per-user auto-memory), and the
**eval harness** (§9). Design: `docs/architecture.md`.

**Operation families** (host-facing API; deterministic = no model call):

| family | endpoints | model? |
|---|---|---|
| **capture** (perception → memory) | `observe`, `remember`, `consolidate`, `consolidation-status` | deterministic |
| | `ingest` (transcript → observations) | LLM |
| **recall** (memory → host) | `select`, `units`, `timeline` | deterministic |
| **cognition / maintenance** (the Dream) | `reflect`, `plan`, `reconcile`, `curate`, `detect-contradictions`, `infer-deps`, `infer-temporal`, `dream` | LLM |
| | `consolidate`, `compact` | deterministic |

‹TODO figure: unit → graph → operations; the host/kernel boundary with perception/action/time on the
host side and the typed graph + pure operations on the kernel side.›

- Source: `src/aigg_memory/server.py` (`_ROUTES`), `docs/architecture.md`.

## 4. A bitemporal, typed, provenance-carrying memory graph

The atom of memory is a **unit** at `‹corpus›/‹slug›/SKILL.md`: a YAML frontmatter of typed metadata
plus a markdown body. Units in a corpus form a directed graph via typed edges. Everything later
sections rely on — kind-aware policy, provenance audit, valid-time queries, stale-propagation — is
metadata on this one structure, versioned by git.

**Kinds** (`VALID_KINDS`): `procedural`, `semantic`, `episodic`, `working`, **`belief`**, **`plan`**,
**`goal`**. Kind is not a label but a *policy carrier*: `belief ≠ fact` (a generalization is never
ground truth), `procedural` memory is treated conservatively, `plan` is an intention the kernel never
enacts, `goal`/`belief` are what planning may seed from (§5). The last three kinds are what let
reflection and planning live in the same store as the facts they range over.

**Typed edges** (`_REL_FIELD`): `deps` (depends_on), `references`, `supersedes`, `precedes`, and
**`derived_from`**. `precedes` records world-time ordering git's commit order cannot express;
`supersedes` records correction; **`derived_from` records justification** — it is the edge reflection
and planning write and stale-propagation walks (§5). The graph *is* the dependency structure; there is
no separate index of "what rests on what."

**Provenance**: `asserted_by` (who asserted it — a principal / EOA id, or `self` for a synthesized
belief) and `source_events` (the events it was distilled from). Provenance is load-bearing, not
decorative: it powers audit ("did this NPC really learn this, or hallucinate it?"), the
**faculty/social split** in discernment (a belief I asserted myself vs. one a peer warned me with),
and the relay-traceability probes.

**Two independent time axes (bitemporal).** Memory separates *when a fact was recorded* from *when it
holds in the world*:
- **Transaction-time = git.** Every change is a commit; "what did the agent believe at time C?" is
  `git checkout C`. History is immutable and auditable for free.
- **Valid-time = `valid_from` / `valid_to`.** "When does/did this fact hold?" Queried by
  `index.timeline()` (units ordered by `valid_from`) and `index.as_of(when)` (units valid at a
  world-time). Plans carry a **future** `valid_from` (≥ `now`); a fact that is corrected gets its old
  version stamped `valid_to`, not deleted.

The axes are orthogonal, and `reconcile`'s temporal branch shows why both are needed. When "the party
is at 5pm" is later corrected to "5:30pm", reconcile does **not** overwrite: it stamps the old unit
`valid_to = now`, sets the new unit `valid_from = now`, and archives the old — **non-destructive,
history preserved**. The result is queryable on both axes:

| | transaction-time (git) | valid-time (`valid_from`/`valid_to`) |
|---|---|---|
| question | "what did the agent *know* at commit C?" | "when is the party, *as of* world-time T?" |
| 5pm fact | present from commit C₁ | holds for `valid_from`=T₁ … `valid_to`=T₂ |
| 5:30pm fact | added at commit C₂ | holds for `valid_from`=T₂ … |
| query | `git checkout C₁` reconstructs that snapshot | `as_of(T)` selects whichever fact held at T |

**Guards** (cornerstones the automatic loop must not touch): `locked` — owner-authored units (a
persona card) are off-limits to the auto-loop's overwrite/merge (`_is_locked`); `pinned` — sticky
through merges (a merge never silently unpins a profile); `needs_review` — the destination for any
judgement the kernel is *not confident* about (an unknown contradiction winner goes to a human, it is
never guessed, §8).

- Source: `src/aigg_memory/memory.py` (`VALID_KINDS`, `_REL_FIELD`, `MemoryUnit`, `reconcile`'s
  temporal branch), `src/aigg_memory/index.py` (`timeline`, `as_of`, edge accessors),
  `src/aigg_memory/cli.py` (`timeline` query).

## 5. Mirror synthesis: reflection and planning over one graph

Higher-order cognition in aigg-memory is **two synthesis operations that are mirror images of each
other** over the same typed graph and the same edge type (`derived_from`). One looks backward in time
to explain the past; the other looks forward to commit to a future. Because they share a substrate,
the machinery that maintains one maintains the other.

| | **Reflection** (backward) | **Planning** (forward) |
|---|---|---|
| input | episodes / facts (what happened) | goals + beliefs (what to pursue) |
| output | `kind=belief` (a generalization) | `kind=plan` (an intention) |
| `derived_from` | the evidence the belief generalizes | the goal/facts the plan reacts to |
| time | about the past/atemporal | **future `valid_from`** (≥ `now`) |
| `asserted_by` | `self` | `self` |
| status | active (belief) | `candidate` (never auto-acted) |
| entry point | `reflect()` | `plan()` |

**Reflection.** `reflect()` clusters similar units (an embedder + threshold), and for each cluster the
model synthesizes a `kind=belief` unit whose `derived_from` cites the cluster members and whose
`asserted_by` is `self`. Two invariants hold: **belief ≠ fact** (a synthesized generalization is never
recorded as ground truth), and **a belief with no cited sources is dropped** — no inventing evidence
(`parse_reflections` requires a non-empty `derived_from`). Design: `docs/reflection_design.md`.

**Planning.** `plan()` is the dual. It is **seeded** from explicit `goals`, else `kind=goal` units,
else (fallback) the active beliefs; the planner's context is the seeds *plus the agent's active facts
and beliefs* (§7), so a plan can be **grounded in, and cite, the facts it is reacting to** — not just
its goals. Each `kind=plan` unit carries a **future `valid_from`** (clamped to ≥ `now`: an intention
is forward, never back-dated) and a `derived_from` validated against existing slugs (a plan that cites
no real rationale is dropped). The plan is `status=candidate`; **the kernel never acts on it** —
enacting an intention is the host's job. Design: `docs/planning_design.md`.

**Stale-propagation — one mechanism, two payoffs.** Both operations write `derived_from` edges, so the
graph records *what rests on what*. `mark_stale_dependents()` walks those edges in reverse: when a unit
is superseded, every unit transitively `derived_from` it is flagged `stale`. The same traversal
therefore delivers:
- **belief revision** — supersede a fact, and the beliefs generalized from it go stale; and
- **replanning** — change a fact or belief, and the plans built on it go stale,

with **no replan-specific code**. Stale-propagation is invoked wherever the truth shifts — `reconcile`
(a new statement corrects or temporally supersedes an old one) and `detect_contradictions` both return
the set they marked. A `stale` flag is a *request for re-synthesis*, not an edit: the kernel never
silently rewrites; the next reflect/plan pass (or the host) decides.

**Worked example (the coordination chain).** Isabella's party: each guest's `goal_socialize` plus the
relayed `invite_party` fact seeds a `plan` whose `derived_from = [goal_socialize, invite_party]` and
`valid_from = ` party time. When the time changes, `reconcile` supersedes `invite_party`;
stale-propagation walks `derived_from` backward and flags every dependent attend-plan for replan —
across all NPCs, zero bespoke code. The `no_reconcile` ablation leaves the plans un-flagged, isolating
the mechanism. (This is also where the **fact-in-context** requirement was found: if `plan()` does not
surface `invite_party` to the planner, the plan can't cite it and the chain silently breaks — §9.)

**The seed requirement.** Planning is goal/belief-seeded by design: *facts alone are context, not a
seed* — there is nothing to plan *toward*. When no seed exists `plan()` returns early (the model is not
even called) with an actionable `diagnostics` message rather than a bare empty list (§9, gap 9).

‹TODO figure: the backward/forward mirror sharing `derived_from`; the stale wavefront propagating from
a superseded fact through beliefs to plans.›

- Source: `src/aigg_memory/memory.py` (`reflect`, `plan`, `mark_stale_dependents`, `reconcile`,
  `consolidate_corpus`, `dream`); `src/aigg_memory/extract.py` (`parse_reflections`, `parse_plans`);
  tests `tests/test_reflection.py`, `tests/test_planning.py`.

## 6. Provenance-based cognition: decide by evidence, not text

A host reads memory to *decide*: does this agent believe the pump is a trap? does it distrust this
caller? The naive implementation matches the decision keyword against the belief's text. That works
for a scripted model and fails for a real one, because **a real model words the same belief
differently every run.** Reflecting twice over the identical burn-episodes, `gemma4` produced beliefs
slugged `pattern_of_avoiding_pump_schemes`, then `avoidance_of_scams` (no "pump", no "trap" at all),
then `susceptibility_to_pump_scams`; the anti-manipulation belief came back as
`pattern_of_shilling_misinformation`, then `negative_consequence_of_following_shill`, then
`avoidance_of_hype_driven_investments` (no "shill", no "manipulator"). A keyword decision silently
misses these, and the agent "forgets" what it learned.

**Embeddings are not the fix.** One might recall the belief semantically instead. We measured cosine
similarity (real `all-MiniLM-L6-v2`, not the kernel's default hash embedder) of the 2-word decision
query `"pump trap"` against candidate beliefs:

| belief text | cosine vs `"pump trap"` |
|---|---|
| `"pump offers are pump-and-dump traps to avoid"` (shares tokens) | **+0.753** |
| `"deceptive offer patterns: schemes operating as inherently deceptive mechanisms causing loss"` | **+0.135** |
| `"the weather is nice and I enjoy a cup of coffee"` (unrelated) | −0.005 |

The reworded belief — exactly the kind a real model emits — scores **0.135**, below any usable
threshold and barely above noise. A short decision query produces a noisy embedding; the semantic
overlap exists conceptually but is swamped by surface form and length. Semantic recall helps only when
query and belief already share enough context, so it is *query-dependent*, not a silver bullet — and
it drags in an embedding model the decision otherwise does not need.

**The mechanism — read the evidence, not the words.** `believes` / `discernment` take a `mode`:

| mode | "is this belief about X?" | wording-robust | needs LLM | needs embedding |
|---|---|---|---|---|
| `text` (default) | substring of the belief's own text | ✗ | ✗ | ✗ |
| (semantic) | cosine of query vs belief, real embedder | ~ (query-dependent; 0.135 above) | ✗ | ✓ (torch) |
| **`provenance`** | the belief is `derived_from` evidence about X | **✓** | ✗ | ✗ |

In **provenance mode** a belief is *about X* iff one of its `derived_from` sources is about X
(`_about()` in `agent.py`). **A belief is what its evidence is, whatever words the synthesis chose.**
The burn-episodes carry the topic (`burn_pump_*`, `match=[pump, trap, …]`); a belief that drops the
words entirely is still recognized through the episodes it cites. The check is a graph lookup —
deterministic, **no LLM and no embedding** — over structure the kernel already has.

**Result.** Carrying the decision through provenance mode, the discernment experiments reproduce **3/3
over a real local model** despite per-run wording variation: E1 (learning curve) yields the same
`[0,0,1,1,1,1,1,1]` curve (burns 8→2) whatever the belief is named, and E5 (anti-manipulation) yields
rugged 2/8 with the honest caller still followed 8/8. The regression test
`test_provenance_mode_is_robust_to_wording` encodes the core case: a belief whose *own text* omits the
topic is still caught via its evidence, while `text` mode misses it.

**Honest boundary.** Provenance fixes *wording* robustness, not *reasoning* robustness — it requires
the model to cite the right `derived_from` in the first place. Citing the right rationale is the real
reliability frontier (§7, §11), and it is a kernel-context problem before it is a model problem (§5
seed/context).

- Source: `src/aigg_memory/agent.py` (`_about`, `believes`, `discernment`), `tests/test_agent_client.py`,
  eval `examples/eval/README.md` (§"the three discernment modes").

## 7. Model-agnostic extraction (cheap local models, not one vendor)

- **Tolerant parsing.** Small models wrap JSON in a ```json fence *and* add prose; parsers pull the
  first JSON value out of fenced+prose replies (`json.JSONDecoder().raw_decode`). Cloud bare-JSON
  parses identically. Applies to observe/edges/contradictions/reconcile/curate/reflect/plan.
- **Field coercion.** `body` returned as an object/list → JSON string; `match` as a string → `[str]`.
- **Per-operation model routing.** Each operation takes its own `{backend, model}`; the *hard*
  structured ops (plan/reconcile) can use a stronger model than the *cheap* ones (reflect). The
  kernel already accepts `model`/`backend` per endpoint; the harness exposes per-op overrides.
- **Backends.** OpenAI-compatible HTTP (incl. **Ollama**), and `claude -p` (note: agentic — needs
  `--system-prompt` override, not `--append-system-prompt`).
- ‹TODO: the "it's the kernel, not the model" finding — even a strong model can't cite a fact the
  planner never put in context (§5 seed/context); the fix was surfacing facts, not a bigger model.›
- Source: `src/aigg_memory/extract.py` (`_loads_json`, `_normalize_observation`, `AIGG*`).

## 8. Epistemic conservatism as invariants

aigg-memory is meant to run **unattended** — a nightly "Dream" pass mutates an agent's memory with no
human in the loop. That is only safe if the operations are *conservative by construction*: every
ambiguous case must fail toward **defer / keep / ask**, never toward **destroy / fabricate / overwrite**.
We encode a single stance — **when uncertain, defer; never guess** — as concrete invariants, each
averting a specific way an automatic loop could corrupt memory.

| invariant | mechanism | failure it averts |
|---|---|---|
| **uncertain → `needs_review`, not a guess** | an unknown/invalid contradiction winner is routed to `needs_review` (and locked), not auto-resolved ("ask a human, don't guess") | a confident-but-wrong merge silently rewriting truth |
| **reconcile defers** | an unrecognized relation degrades to `relation=uncertain` rather than picking one | a bad correction/temporal-supersede on a coin-flip |
| **parse ambiguity → keep** | a missing/unknown curation verdict degrades to `keep` | a parse glitch causing a *deletion* |
| **degrade, don't crash** | every parser returns `[]` / `uncertain` on unparseable output (§7), never raises | one malformed model reply aborting a maintenance pass |
| **belief ≠ fact** | synthesized beliefs are `kind=belief`, `asserted_by=self` — never recorded as ground truth | a generalization hardening into an unsourced "fact" |
| **no evidence → dropped** | a belief/plan with empty `derived_from` is discarded (no inventing justification) | hallucinated cognition entering the store |
| **plans never auto-act** | a plan is `status=candidate`; enacting is the host's job | the memory layer taking world actions on its own |
| **non-destructive correction** | temporal supersede stamps `valid_to` and archives, never deletes (§4) | losing history / unauditable edits |
| **owner cornerstones are off-limits** | `locked` units (persona cards) are never overwritten/merged; `pinned` survives merges | the auto-loop eroding human-authored identity |
| **ambient capture is gated** | promotion needs repetition (`min_promote_count`, default 2); a one-off is chatter | every passing remark becoming a permanent memory |

Two design choices follow from the table and are worth stating explicitly.

**Confidence is graded, with an explicit fast path.** Ambient observation is deliberately slow (it
waits for repetition) so noise does not accrete; but a *deliberate* fact — a host that knows it wants
to remember this — takes the single-shot path (`min_count=1`, or `/memory/remember`) and lands
immediately. The gate is on *uncertain* capture, not on *confident* capture.

**Tolerance and conservatism point the same way.** The tolerant parsing of §7 is not just an
ergonomic fix; it is conservative-by-design. A small model's malformed reply degrades to "extracted
nothing this pass" — a no-op — rather than to a deletion or a fabricated unit. Robustness to messy
input and safety under automation are the same property: *the worst outcome of any ambiguity is that
memory is unchanged.*

- Source: `src/aigg_memory/memory.py` (`detect_contradictions` → `needs_review`, `reconcile`,
  `_is_locked`, repetition gate), `src/aigg_memory/extract.py` (`parse_reconciliation`,
  `parse_curation` degrade-safe defaults).

## 9. Two-tier evaluation methodology

We evaluate the kernel at **two tiers**, and we claim the *pairing* is the contribution.

**Tier 1 — deterministic stub (the CI gate).** A scripted model returns fixed structured output for a
given prompt, so every experiment is a pure function of the store. This tier validates **architecture
and math**: that reflection synthesizes the right `derived_from`, that stale-propagation reaches every
dependent, that the diffusion/coordination probes compute what they should. It is fast, free, and
reproducible — the suite (`pytest`, the manifest runner) is a hard gate.

**Tier 2 — real local model (the judgment probe).** The same experiments run with `--real` against a
real model (Ollama `gemma4`, free and local; or `claude -p`), budget-capped. This tier validates
**judgment quality** — does a real reflect actually form the trap-belief? — and, crucially, **surfaces
engineering gaps the stub cannot**, because the stub by construction emits clean, well-formed,
schema-perfect output that no real model reliably produces.

**What reproduces, and what does not.** Single-step operations reproduce *reliably*: a reflect that
forms one belief from a cluster of episodes passes 3/3 over `gemma4` (the wording varies; provenance
mode reads through it, §6). **Multi-step causal chains are brittle** — but the brittleness is
diagnostic, not fatal. Running the coordination experiment, `plan`/`reconcile` execute and diffusion
holds, yet the chain initially broke: the guest's plan cited only its goal and **omitted the
invitation it was reacting to**, so superseding the invitation did not flag the plan stale. The cause
was *not* model quality — a strong cloud model (`sonnet`) omitted the invitation too — it was that
`plan()` never put the invitation in the planner's context (§5). Surfacing the agent's facts fixed it,
and then **the cheap `gemma4` cited the invitation correctly** and the stale-replan chain fired. *It is
the kernel, not the model.*

**The gaps the real-model tier surfaced.** Each row below is invisible to a deterministic stub (the
stub never fences its JSON, never reworded a belief, never under-cited a rationale, never timed out),
and each became a kernel or DX hardening. We present the table as the concrete output of the
methodology:

  | # | Gap surfaced by a real (local) model | Fix | Invisible to a stub because… |
  |---|---|---|---|
  | 1 | `claude -p` is agentic; ignores appended JSON instructions | `--system-prompt` override + exclude dynamic sections | stub has no agentic persona |
  | 2 | decisions string-matched belief text → brittle to wording | provenance mode (decide by `derived_from`) | stub belief always has the keyword |
  | 3 | planner couldn't cite a fact it never saw → broken causal chain | `plan()` context includes the agent's active facts | stub cites the right slug by script |
  | 4 | small-model fenced+prose JSON dropped → empty reflect/plan | tolerant `_loads_json` across all parsers | stub returns bare JSON |
  | 5 | single deliberate observation never promoted | `/memory/consolidate` honors `min_count` | stub tests seeded ≥2 observations |
  | 6 | no one-call "write a fact" entry for a host | `/memory/remember` (deterministic) | host ergonomics, not a stub concern |
  | 7 | small model returns `body` as an object → unit write breaks | `_normalize_observation` field coercion | stub returns `body` as a string |
  | 8 | cold local model exceeds the fixed 30s timeout | per-request `timeout` (reflect/reconcile/plan/ingest + eval→serve) | stub replies instantly |
  | 9 | empty `plan()` gave no reason (no goal seed) | actionable `diagnostics` in the plan result | stub corpora always seeded a goal |

**Takeaway.** A deterministic harness is necessary (it pins the math and gates CI) but **structurally
blind** to the failure modes that only a real, non-deterministic, imperfect model produces. The second
tier is cheap — a free local model — and it is where the design met reality: nine of the kernel's
robustness properties exist *because* a real model exercised them. We recommend this pairing for any
LLM-backed system: deterministic for *correctness*, real-but-cheap for *robustness*.

- Source: `examples/eval/` (harness, manifests, probes, `experiment_*.py`); `examples/eval/README.md`.

## 10. Evaluation

‹TODO pull concrete numbers from the eval; keep the *full* E1–E9 + emergences for the applied paper,
use a compact subset here to demonstrate mechanisms.›
- **E1 — discernment learning curve.** memory ON learns to avoid the recurring trap (`[0,0,1,1,1,1,1,1]`,
  burns 8→2) and stays selective; OFF stays flat. Real `ollama/gemma4`: 3/3.
- **E5 — anti-manipulation immunity.** per-caller distrust from provenance; rugged 2/8, honest-caller
  followed 8/8. Real: 3/3.
- **Coordination chain (mechanism demo).** invite → plan(cites invite) → time-change → reconcile →
  stale-propagation flags the dependent plan; the `no_reconcile` ablation flips it.
- **(Pointer) full E1–E9 + three Smallville emergences** → applied paper.
- **Cost/latency.** stub: deterministic, free. `ollama/gemma4`: local, free; per-call ~seconds.

## 11. Limitations & future work

- Provenance decisions need correct `derived_from` from the model; a cheap model's *structured
  reasoning* (citing the right rationale) is the reliability frontier, not its wording.
- HashEmbedder is non-semantic by default; real-embedding recall is opt-in (and not a silver bullet
  for short queries).
- Context is capped (top-N); relevance filtering for large corpora is future work.
- ‹TODO: scale (many NPCs / large corpora), conflict resolution beyond temporal/supersede, learned
  consolidation policy, eval beyond two scenarios.›

## 12. Conclusion

‹TODO: one substrate — typed, versioned, provenance graph — yields belief revision, planning, audit,
and model-agnostic cognition; the two-tier eval is how we kept it honest.›

---

## Appendix A — API surface (host-facing)

`/memory/{observe, consolidate, remember, select, units, reflect, plan, reconcile, curate, ingest,
dream, …}`. ‹TODO: one line each: deterministic vs LLM; required fields; returns.› Source:
`src/aigg_memory/server.py` (`_ROUTES`).

## Appendix B — Reproducibility

- Stub (CI): `PYTHONPATH=src python3 -m pytest -q`; `python3 examples/eval/run.py ‹manifest›`.
- Real local model: `AIGG_EVAL_REAL=1 AIGG_EVAL_BACKEND=ollama AIGG_EVAL_MODEL=gemma4:latest …`.
- ‹TODO: pin versions; list manifests; expected probe values.›

## Appendix C — Source map

‹TODO table: claim/section → file:symbol, so a reader can trace every claim to code and tests.›
