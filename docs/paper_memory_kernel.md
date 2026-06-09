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

- The unit: `‹corpus›/‹slug›/SKILL.md` — YAML frontmatter (typed metadata) + markdown body.
- The graph: a **MemoryMakefile** of units linked by typed edges; the kernel is a set of pure
  operations over corpus snapshots; the host owns the loop and the clock.
- Boundary: kernel = cognition substrate; host (MUD / inference gateway / plugin) = perception,
  action, time. ‹TODO figure: unit → graph → operations; host/kernel boundary (see `docs/architecture.md`).›

## 4. A bitemporal, typed, provenance-carrying memory graph

- **Kinds** (`VALID_KINDS`): procedural / semantic / episodic / working / **belief / plan / goal**.
  Kind drives policy (e.g. procedural → `needs_review`; belief ≠ fact; plan never auto-acts).
- **Typed edges** (`_REL_FIELD`): `deps`, `references`, `supersedes`, `precedes`, **`derived_from`**.
  The graph is the dependency structure planning/reflection traverse.
- **Provenance**: `asserted_by`, `source_events` — who said it, from what. Enables audit and the
  faculty/social split (self-asserted vs peer-asserted).
- **Valid-time**: `valid_from` / `valid_to` with `as_of` timeline queries — *when the fact holds*,
  distinct from *when it was recorded*.
- **Transaction-time**: git history — every change is a commit; time-travel is `git`.
- **Guards**: `locked`, `pinned`, `needs_review` — cornerstones the auto-loop won't rewrite.
- ‹TODO: the bitemporal table (transaction-time × valid-time) with a worked example.›
- Source: `src/aigg_memory/memory.py` (`VALID_KINDS`, `_REL_FIELD`), `index.py` (graph accessors).

## 5. Mirror synthesis: reflection and planning over one graph

- **Reflection (backward).** `reflect()` clusters episodes/facts and synthesizes `kind=belief` units
  with `derived_from` pointing at their evidence, `asserted_by="self"`. Belief ≠ fact invariant; a
  belief with no cited sources is dropped (no inventing evidence). Design: `docs/reflection_design.md`.
- **Planning (forward).** `plan()` is the dual: seed from `kind=goal` (else beliefs), synthesize
  `kind=plan` units with **future `valid_from`** (clamped ≥ `now`) and `derived_from` citing the
  goal/facts they react to. The kernel **never acts** on a plan. Design: `docs/planning_design.md`.
- **Stale-propagation = one mechanism, two payoffs.** `mark_stale_dependents()` walks reverse
  `derived_from`; when a fact is superseded, every belief built on it — and every plan built on those
  beliefs — is flagged stale. **Belief revision and replanning are the same code.**
- **The seed requirement** (surfaced empirically, §9): planning is goal/belief-seeded; *facts alone are
  context, not a seed* — `plan()` emits a diagnostic when no seed exists.
- ‹TODO figure: the backward/forward mirror; the stale wavefront along `derived_from`.›
- Source: `memory.py` (`reflect`, `plan`, `mark_stale_dependents`, `reconcile`, `consolidate_corpus`).

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

- **Uncertain → defer, never guess.** Parse failure degrades to keep/uncertain, *never* deletion;
  reconcile returns `uncertain` rather than a wrong merge.
- **belief ≠ fact**; `asserted_by="self"` on synthesized beliefs; a belief/plan with no cited evidence
  is dropped.
- **Plans never auto-act** — `kind=plan`, `status=candidate`; enacting is the host's job.
- **Repetition gate** for ambient capture (`min_promote_count`), with an explicit single-shot path
  (`min_count=1`, `/memory/remember`) for deliberate facts.
- ‹TODO: argue these invariants are what make an *automatic* memory loop safe to run unattended.›

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
