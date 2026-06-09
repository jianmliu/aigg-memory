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

**Problem.** LLM agents need durable memory, and the dominant pattern is to embed text and recall the
top-k by similarity. That pattern throws away four things a cognizing agent actually needs: the *type*
of a memory (a fleeting observation vs. a durable belief vs. a future intention), its *provenance*
(who asserted it, from what), its *time* (when it holds in the world, vs. when it was recorded), and
its *causal structure* (what rests on what). Without them, belief revision, replanning, and audit are
re-implemented per application, and an automatic memory loop has no principled way to revise, expire,
or justify what it stores.

**Thesis.** Represent memory not as a bag of vectors but as a **typed, git-versioned, provenance-carrying
dependency graph**, with a small set of pure operations over it. We show that the capabilities usually
bolted on — belief revision, planning, audit, expiry, and model-agnostic decision-making — fall out of
this one substrate. In particular, reflection and planning become *mirror images over the same graph*,
and a single traversal of one edge type delivers both belief revision and replanning.

**Contributions** (each maps to a section):
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
**What we do not claim.** This is not a new retrieval method — we use a deterministic hash embedder by
default and do not compete on top-k recall quality. It is not a new model — the contribution is the
substrate and its operations, which run over *any* sufficiently instruction-following model, cloud or
local. And it is not a finished agent — the kernel supplies cognition; perception, action, and the
clock stay with the host (§3). The claim is narrow and structural: *typing, versioning, and provenance,
plus mirror synthesis, turn a pile of remembered text into a memory that can revise, plan, and be
audited — on a free local model.*

## 2. Related work

*Full bibliographic entries in **References** (verified June 2026).*

**Agent memory and generative agents.** Generative Agents (Park et al., 2023; arXiv:2304.03442) is the
closest: a *memory stream* of natural-language observations retrieved by recency × importance ×
relevance, with periodic *reflection* into higher-level statements and *planning* into a daily
schedule. We share the reflect-and-plan loop but differ in representation: the memory stream is a flat,
append-only log with a scalar importance, whereas our memory is a **typed, versioned, provenance graph**;
their reflection and planning are separate procedures, whereas ours are **mirror operations over one
graph** whose `derived_from` edges give belief revision and replanning from a single traversal (§5).
MemGPT (Packer et al., 2023) is complementary, not competing: it manages *where* memory lives
(an OS-style hierarchy paging between context window and external store), while we manage *what* a
memory *is* (type, provenance, time, causal structure). RAG/vector memory (e.g. LangChain/LlamaIndex
memory modules; and Letta, the model-agnostic stateful-agents framework that productized MemGPT) is the embed-and-recall baseline the introduction contrasts against.

**BDI and planning.** The goal→intention move in `plan()` echoes the Belief-Desire-Intention tradition
(Bratman, 1987; Rao & Georgeff, 1995), where agents commit to intentions derived from beliefs
and desires. Classical BDI uses symbolic plan libraries and logical entailment; we synthesize
intentions with an LLM and ground them in a provenance graph, so *commitment* is a typed unit with a
future `valid_from` and a cited rationale, and *reconsideration* is stale-propagation rather than a
re-planning meta-policy.

**Truth maintenance and belief revision.** Justification- and assumption-based truth maintenance
(Doyle, 1979; de Kleer, 1986) track which conclusions rest on which justifications and retract
them when support is withdrawn — and AGM belief revision (Alchourrón, Gärdenfors & Makinson, 1985) formalizes consistent update. `derived_from` + `mark_stale_dependents` is a lightweight,
LLM-era JTMS: justifications are `derived_from` edges, retraction is stale-propagation. We deliberately
do *less* than a classical TMS — no logical solver, no global consistency guarantee — and instead emit
a `stale` flag that *requests re-synthesis*, which fits a substrate whose "inferences" are LLM
generalizations rather than entailments.

**Bitemporal data and provenance.** Separating *valid-time* from *transaction-time* is standard in
temporal databases (Snodgrass, 1999; the bitemporal model). Our contribution is the mapping
for agent memory: **transaction-time = git history** (auditable, time-travelable for free) and
**valid-time = `valid_from`/`valid_to`** (queried by `as_of`/`timeline`), with non-destructive temporal
supersede (§4). Data provenance / lineage (why-, how-, where-provenance; Buneman et al., 2001; Cheney
et al., 2009) motivates `asserted_by`/`source_events`; our novelty is using *why-provenance at
decision time* — a belief is judged by its evidence, not its text (§6).

**Versioned data stores and typed prompt artifacts.** Using git directly as the store relates to
git-as-database systems (e.g. Dolt, "Git for data"); we exploit commits as transaction-time rather than
building a new versioning layer. Finally, each unit *is* a `SKILL.md` — the same typed,
frontmatter-plus-markdown artifact used for agent *capabilities* (the Agent Skills / `SKILL.md`
open standard, Anthropic 2025) — so an agent's memory and its skills share one representation, and a learned
belief can in principle become an invokable skill.

**Positioning.** We are not proposing a better retriever or a new model; we adopt known ideas — temporal
databases, truth maintenance, provenance, generative-agent reflection/planning — and unify them on one
git-versioned typed-graph substrate, then show (§9) that running it on a *free local model* is what
forces the design to be honest.

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

Cognition should not be hostage to one API. The LLM-backed operations (`ingest`, `reflect`, `plan`,
`reconcile`, `curate`, …) each reduce to "send a prompt, parse a structured reply", so in principle any
instruction-following model serves. In practice a *small, free, local* model — the case that makes
per-NPC memory affordable at the scale of a town — produces messier output than the cloud model the
prompts were tuned against, and a strict pipeline silently drops it. The kernel's extraction layer
absorbs that messiness so the operations are model-agnostic *in fact*, not just in principle. Every
hardening below was surfaced by running against Ollama `gemma4` (§9).

**The envelope problem → tolerant parsing.** A cloud model returns bare JSON; a small model wraps it
in a ```json fence *and* often adds prose ("Sure! Here are the beliefs: ```json […]``` Let me know…").
The original parsers stripped a fence only when it wrapped the *entire* reply, so fenced-in-prose
parsed to nothing — `reflect`/`plan` returned empty and the agent appeared to learn nothing. The fix
is one shared helper, `_loads_json`: locate a fenced block anywhere, then parse the first JSON value
with `json.JSONDecoder().raw_decode`, which ignores trailing prose. It is applied to every parser
(observations, edges, contradictions, reconcile, curate, reflect, plan). A bare-JSON cloud reply
parses identically, so the strict path is unchanged — tolerance is strictly additive.

**The field-type problem → coercion.** Even with valid JSON, a small model fills fields off-shape:
`gemma4` returned a plan/observation `body` as a JSON *object* (`{"time":"dawn",…}`) and `match` as a
bare string. A `body` that is not a string breaks the unit write downstream. `_normalize_observation`
coerces: a non-string `body` is serialized to a string, a string `match` becomes `[str]`. Robustness
to off-type values, like tolerance to messy envelopes, degrades a bad reply to "extracted nothing",
never to a crash or a malformed unit (§8).

**The backend problem.** Two transports are supported: an OpenAI-compatible HTTP endpoint (covering
**Ollama** directly — a plain `/v1/chat/completions` call that follows "return only JSON") and
`claude -p`. The latter surfaced a sharp gap: `claude -p` is the *agentic* Claude Code, not a raw
completion endpoint, so with `--append-system-prompt` it answers conversationally and ignores
"return only JSON". The fix is to use `--system-prompt` (override) plus
`--exclude-dynamic-system-prompt-sections`, turning it back into a clean structured extractor.

**Per-operation routing.** Operations differ in difficulty: forming one belief from a cluster
(`reflect`) is easy; selecting the right rationale among candidates (`plan`, `reconcile`) is hard. The
kernel already accepts `{backend, model}` per endpoint, so a host can route the *hard* ops to a stronger
model and keep the *cheap* ops local. The eval harness exposes this as per-operation overrides
(`AIGG_EVAL_BACKEND_PLAN=claude-cli` while `reflect` stays on `ollama/gemma4`).

**The central finding: it is the kernel, not the model.** Per-op routing tempts a simple story —
"send the hard ops to a bigger model." It is wrong. When the coordination chain broke because the
guest's plan omitted the invitation it was reacting to (§5, §9), we routed `plan` to a strong cloud
model (`sonnet`); it omitted the invitation *too*. The cause was not model strength but that `plan()`
never put the invitation in the planner's *context* — and once the kernel surfaced the agent's facts,
the **cheap `gemma4` cited it correctly** and the chain fired. Model-agnosticism, then, is won mostly
on the kernel side: get the context, the prompt contract, and the parsing right, and a free local model
suffices for most operations; reserve a stronger model for the genuinely harder judgments, not as a
patch for a kernel that failed to show the model what it needed.

- Source: `src/aigg_memory/extract.py` (`_loads_json`, `_normalize_observation`, the `AIGG*`
  extractors and the `claude-cli` transport); tests `tests/test_tolerant_parse.py`; the gaps table (§9).

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

We demonstrate the mechanisms on a compact subset and report both tiers (§9). The full economic
(E1–E9) and Smallville emergence batteries belong to the applied paper; here the goal is to show that
the substrate's claims hold, and hold *on a free local model*. All stub results are deterministic;
real results use Ollama `gemma4` (free, local), one model call per experiment.

| experiment | what it tests | memory ON (stub) | memory OFF (stub) | real `ollama/gemma4` |
|---|---|---|---|---|
| **E1** discernment learning | learn to avoid a recurring trap, stay selective | curve `[0,0,1,1,1,1,1,1]`, **burns 8→2**, good-engaged 8/8 | flat `[0,…]`, burns 8 | **identical curve every run** |
| **E5** anti-manipulation | distrust a manipulator, keep trusting the honest caller | **rugged 2/8**, honest-followed 8/8 | rugged 8/8 | **identical every run** |
| **coordination** chain | invite→plan→time-change→reconcile→stale-replan | all 5 probes pass; `no_reconcile` ablation flips `stale_replan` **2→0** | — | chain **fires** (see below) |

**E1 — discernment learning curve.** With memory the agent is burned twice, reflects the trap-belief,
and avoids it thereafter (`[0,0,1,1,1,1,1,1]`, burns 8→2) while still engaging the genuine opportunity
(8/8) — it learns without becoming paranoid. Without memory it is burned all 8 rounds. The decision is
read through **provenance mode** (§6), so the curve is identical on the real model *even though the
synthesized belief is worded differently every run* — across this session `gemma4` named it
`avoidance_of_manipulative_investment`, `historical_financial_risk_pattern`, `avoidance_of_scams`,
`susceptibility_to_pump_scams`, … (several without the words "pump" or "trap"), and every one drove the
same curve because the decision reads the belief's evidence, not its text.

**E5 — anti-manipulation immunity.** A `shill` repeatedly issues losing calls; an honest `oracle` does
not. Memory forms a per-caller "manipulator" belief from the rug-episodes (again via provenance), so the
agent stops following the shill after two rugs (rugged 2/8) while still following the oracle (8/8);
without memory it is rugged all 8. Real `gemma4`: identical, with the belief variously named
`warning_against_hyped_shill_advice`, `pattern_of_avoiding_overhype_investment_calls`,
`pattern_of_shilling_misinformation`, … — provenance reads through all of them.

**Coordination chain (mechanism demo).** Isabella's party (§5): on the stub, all five probes pass —
host planned, 4 NPCs knew, 2 intended (a plan valid by party time), 2 stale-flagged after the time
change, and every relayed copy is provenance-clean; the **`no_reconcile` ablation flips `stale_replan`
2→0**, isolating reconcile + stale-propagation as the cause. On the real model the chain **fires** —
after the kernel surfaces facts to the planner (§7), `gemma4` writes an attend-plan that cites the
invitation, so superseding the invitation flags it stale (`stale_replan` goes from 0 to firing). The
exact 2/2 counts remain brittle on the real model (each guest's plan varies in wording and
`valid_from`), so the deterministic stub stays the source of truth for the precise dynamics while
`--real` confirms the mechanism is real (§9).

**Cost and latency.** The stub tier is deterministic and free (the `pytest` suite — 184 tests — and the
manifest runner gate CI). The real tier is also free: `ollama/gemma4` runs locally, ~seconds per call,
one call per experiment; the harness is budget-capped and skips ablations in real mode. No cloud spend
is required to validate the design on a real model.

**(Pointer.)** The full E1–E9 memory-economics battery and the three reproduced Smallville emergences
(information diffusion, relationship formation, coordination) are evaluated in the applied paper
(`docs/memory_economy_research.md`, `docs/mud_emergence_eval.md`); they use this kernel unchanged.

## 11. Limitations & future work

**Reasoning, not wording, is the frontier.** Provenance-based cognition (§6) makes decisions robust to
*how* a model words a belief, but it depends on the model citing the *right* `derived_from` in the
first place. A cheap local model's structured reasoning — selecting the correct rationale among
candidates, not omitting the fact it is reacting to — is the real reliability ceiling, and it is partly
a kernel problem (surface the right context, §5/§7) and partly a model-capability problem we do not
solve. Per-operation routing (§7) lets a host spend a stronger model where it matters, but quantifying
*which* operations need *how much* model is open.

**Recall is intentionally minimal.** The default hash embedder is non-semantic; real-embedding recall
is opt-in and, as §6 shows, not a silver bullet for short queries. We treat retrieval quality as
orthogonal to the contribution, but a serious deployment will want a stronger retriever, and how that
interacts with the provenance decision path is unexplored.

**Scale.** Context is currently capped (top-N units to the planner); relevance filtering, summarization
of large corpora, and partitioning a town of NPCs are future work. The git-per-corpus model is simple
but its cost at thousands of units / frequent commits is unmeasured.

**Coverage.** Conflict resolution handles correction and temporal supersede; richer conflicts (partial
overlap, multi-party disagreement, confidence-weighted merge) are out of scope here. The consolidation
policy (repetition gate) is hand-set, not learned. And the evaluation is two discernment scenarios plus
a coordination mechanism demo; the full economic and emergence batteries live in the applied paper, and
broader, adversarial, and multi-model evaluation remains to be done.

## 12. Conclusion

We argued that an agent's memory should be a **typed, git-versioned, provenance-carrying dependency
graph**, not a bag of vectors — and that this one substrate yields, rather than bolts on, the
capabilities an autonomous agent needs. Reflection and planning are mirror images over the same graph;
a single stale-propagation along `derived_from` gives belief revision and replanning at once (§5).
Decisions that read a belief's *evidence* rather than its text are robust to a real model's wording and
need no model or embedding at decision time (§6). Tolerant, field-coercing, per-operation extraction
lets the whole thing run on a free local model, not one vendor (§7). And a small set of conservative
invariants — *uncertain → defer, never guess* — make the automatic loop safe to run unattended (§8).

Two methodological commitments kept the design honest. We separated **what a memory should hold** (type,
provenance, time, causal structure) from **how to recall it**, claiming only the former. And we
evaluated at **two tiers**: a deterministic stub that pins architecture and math, and a real but cheap
local model that probes judgment and surfaces the engineering gaps a stub structurally cannot — nine of
the kernel's robustness properties exist because a real model exercised them (§9). We offer that pairing
— deterministic for correctness, real-but-cheap for robustness — as a reusable recipe for building, and
trusting, LLM-backed systems.

---

## References

*Verified June 2026. Classic CS/philosophy entries are canonical; recent/product entries verified
against primary sources (arXiv, official docs/repos).*

- Alchourrón, C. E., Gärdenfors, P., & Makinson, D. (1985). On the Logic of Theory Change: Partial Meet
  Contraction and Revision Functions. *Journal of Symbolic Logic*, 50(2), 510–530.
- Anthropic (2025). *Agent Skills* (open standard; `SKILL.md`). Unveiled Oct 16 2025; opened as a
  standard Dec 18 2025. agentskills.io; "Equipping agents for the real world with Agent Skills".
- Bratman, M. E. (1987). *Intention, Plans, and Practical Reason*. Harvard University Press.
- Buneman, P., Khanna, S., & Tan, W.-C. (2001). Why and Where: A Characterization of Data Provenance.
  *ICDT 2001*, LNCS 1973, 316–330.
- Cheney, J., Chiticariu, L., & Tan, W.-C. (2009). Provenance in Databases: Why, How, and Where.
  *Foundations and Trends in Databases*, 1(4), 379–474.
- de Kleer, J. (1986). An Assumption-based TMS. *Artificial Intelligence*, 28(2), 127–162.
- DoltHub (2019–). *Dolt: Git for Data* — a versioned SQL database. github.com/dolthub/dolt.
- Doyle, J. (1979). A Truth Maintenance System. *Artificial Intelligence*, 12(3), 231–272.
- Letta (formerly MemGPT). *Stateful agents framework* (model-agnostic; memory / reasoning / context).
  letta-ai; github.com/letta-ai/letta.
- Packer, C., Wooders, S., Lin, K., Fang, V., Patil, S. G., Stoica, I., & Gonzalez, J. E. (2023).
  MemGPT: Towards LLMs as Operating Systems. arXiv:2310.08560.
- Park, J. S., O'Brien, J. C., Cai, C. J., Morris, M. R., Liang, P., & Bernstein, M. S. (2023).
  Generative Agents: Interactive Simulacra of Human Behavior. *UIST '23*. arXiv:2304.03442.
- Rao, A. S., & Georgeff, M. P. (1995). BDI Agents: From Theory to Practice. *ICMAS 1995*, 312–319.
- Snodgrass, R. T. (1999). *Developing Time-Oriented Database Applications in SQL*. Morgan Kaufmann.

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
