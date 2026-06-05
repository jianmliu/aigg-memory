# aigg-memory

A **domain-agnostic agent-memory kernel**: the evidence → consolidate → retrieve
loop (plus Dream-style offline consolidation) as a small, reusable library with
**zero dependency on any host framework**. Domains plug in summarizers, appliers,
gates, and detectors; the kernel owns the loop, the data model, and the evidence
store.

> Import package: `aigg_memory` (a hyphen is not a valid module identifier).
> Extracted from [AgentMakefile](https://github.com/jianmliu/AgentMakefile); the
> full pre-extraction history lives in that repository.

## Why

A complete memory system is a *cycle of processes*, not just a store:

| process | component |
| --- | --- |
| **encoding** | `EvidenceStore.record` (observation → evidence) |
| **storage** | typed units (procedural / semantic / episodic) |
| **consolidation = Dream** | `run_dream` — replay evidence, promote, merge, prune |
| **retrieval** | keyword recall over the corpus |
| **forgetting** | prune / archive |

A **skill is a kind of memory** (procedural); a fact is semantic; an event is
episodic. One typed substrate, differentiated by `kind`; consolidation is
kind-aware (procedural lands as `candidate`/needs-review, declarative auto-activates).

## Demo

```bash
python examples/demo.py
```

A ~60-line, dependency-free walk-through — a game NPC remembering a player across
sessions: **encode** (observations) → **consolidate (Dream)** into typed units →
**recall** (semantic + dependency-aware) → **navigate** the dependency graph. No
LLM, no framework, no setup.

## Install

```bash
pip install aigg-memory          # once published
pip install -e .                 # from a checkout
```

Only runtime dependency: PyYAML (for SKILL.md frontmatter). The kernel core
(`models` / `store` / `kernel` / `_util`) is dependency-free.

```bash
pip install "aigg-memory[embedding]"   # adds real semantic embeddings (sentence-transformers)
```

Semantic recall works out of the box with a **zero-dependency** deterministic
feature-hashing embedder (catches morphological / CJK variants that keyword
misses); the extra swaps in a real embedding model. `select(..., retriever=
"keyword" | "semantic" | "hybrid")`; vectors are cached in the index's `vectors`
table (embedded at build time, cosine-ranked at query time).

## Encoding — where memory comes from (extract from transcripts)

Memory starts as raw conversation. The encoding step turns transcripts into
structured observations, which feed the `observe → consolidate` pipeline. The core
stays **model-free**: a deterministic `HeuristicExtractor` baseline, and an
`AIGGExtractor` that routes the real extraction through an external **AIGG**
inference service (OpenAI-compatible, stdlib `urllib` — no new dependency). The app
supplies AIGG's auth + per-task **token-budget** headers, so extraction is a
cost-controlled inference call.

```bash
aigg-memory ingest --transcript chat.txt --evidence ev.jsonl                       # heuristic baseline
aigg-memory ingest --transcript chat.txt --evidence ev.jsonl --extractor aigg \
  --aigg-url https://aigg.example/v1 --aigg-key … --model …                        # extract via AIGG
```

```
raw transcript → extract (model-free baseline / AIGG) → observe → consolidate → typed units
```

## Quickstart — typed unit corpus

```bash
# online: record observations as the agent operates
aigg-memory remember --evidence ev.jsonl \
  --json '{"slug":"budget_protocol","name":"budget_protocol","kind":"semantic",
           "description":"token_budget contract","match":["token budget"],"body":"…"}'
aigg-memory remember --evidence ev.jsonl --json '{…same…}'   # a 2nd observation

# readiness signal — the APP decides when to fire (NPC sleep, session end, epoch)
aigg-memory consolidation-status --root . --evidence ev.jsonl
# -> {"pending":2,"recommended":true,…}

# offline (Dream): promote repeated observations into typed units, gated
aigg-memory consolidate-corpus --root . --evidence ev.jsonl --write
# -> writes memory/budget_protocol/SKILL.md  (kind-aware status)
```

## Quickstart — HTTP API + web UI (`aigg-memory serve`)

```bash
aigg-memory serve --root . --port 8788      # localhost JSON API + a recall UI at /
```

```
POST /memory/observe               record one observation (online, cheap)
POST /memory/consolidation-status  readiness signal (the app owns the trigger)
POST /memory/consolidate           Dream consolidation → typed units (offline)
POST /memory/select                kind-filtered recall + kind-aware bundle
POST /memory/units                 list a corpus
```

A corpus may be nested (`npcs/<id>/memory`), giving each agent/entity its own
memory store and Dream rhythm. This surface is self-contained — an agent (a MUD,
an inference gateway) drives the full online→offline→online cycle over HTTP with
no host framework.

## Compaction — automatic merge, defrag, redundancy removal

Long-lived memory accumulates near-duplicate, fragmented units. Compaction is an
offline pass (app-triggered, like Dream) that clusters near-duplicate units by
semantic similarity, folds each cluster into one canonical unit (union of match +
provenance; `supersedes` records what was folded), and removes the redundant files
(empty dirs too). Conservative by a high `threshold`; dry-run by default.

```bash
aigg-memory compact --root . --threshold 0.85          # dry-run: show what would merge
aigg-memory compact --root . --threshold 0.85 --write  # apply: fold + remove redundancy
```

`POST /memory/compact` exposes the same. This is the forgetting/compression side of
long-term memory: without it the corpus only grows; with it, episodic fragments
fold into coherent units.

## MemoryMakefile — navigate the dependency graph, then edit

Scattered `SKILL.md` files don't tell you *which one to edit* or *what an edit
touches*. The **MemoryMakefile** is the compiled dependency graph (`target:
prerequisites`) — the human navigation view. Units declare relations in
frontmatter (`deps` / `references` / `supersedes`); the graph adds the reverse
edge (`depended_by` = the blast radius).

```bash
aigg-memory graph --root . --write          # compile <corpus>/MemoryMakefile (depends_on / depended_by)
aigg-memory deps budget_protocol --root .   # what it needs + who needs it (blast radius) before you edit
aigg-memory edit budget_protocol --root . --description "…"   # update the unit; returns the blast radius
```

The MemoryMakefile is **derived** (regenerable from the units, which stay the
source of truth) — but unlike the `.aimm-index.db` cache (machine, performance),
it's **for humans**: pick a unit, see its dependencies, edit it knowing what's
affected.

**Dependency-aware recall.** The same graph powers recall: `select` /
`POST /memory/select` with `include_deps` appends a recalled unit's prerequisite
closure (its `depends_on` units, marked `relation: dependency`), so an agent that
recalls "budget" also gets the "token_concept" it depends on — the context is
complete. A consumer (e.g. AgentMakefile) reuses this; it never re-computes the
graph.

## Quickstart — the kernel API (Python)

```python
import aigg_memory as am
from aigg_memory import memory as mem

# a typed memory domain over the multi-file Workspace
records = [...]                                  # list[am.EvidenceRecord]
result = mem.consolidate({}, records)            # pure: workspace in -> out
print(result.gates_ok, result.new_workspace)

# the kernel is domain-agnostic: plug in your own appliers/gates/detectors
domain = am.Domain(name="my-domain", appliers={...}, gates=[...], detectors=[...])
proposals = am.run_dream(domain, records)
patch = am.generate_workspace_patch(domain, proposals_combined, workspace)
```

## Design

- The Dream **trigger is application policy**, not an engine schedule. The kernel
  ships no scheduler; it offers `consolidation_status` as a cheap readiness signal,
  and the app fires `consolidate` at its own moment (an NPC sleeping, a session
  ending, a chain epoch). Per-entity corpora (`npcs/<id>/memory`) give each entity
  its own Dream rhythm.
- Patches generalize from a single document to a multi-file **Workspace**
  (`dict[path → content]`); a single document is the one-entry case.
- Evidence stores a summary + hashes, **never the raw payload**; redaction runs
  before hashing.
- A **derived index** (`<corpus>/.aimm-index.db`, SQLite, stdlib — no new
  dependency) makes recall scale: an inverted `term → slug` table is queried
  instead of re-parsing every `SKILL.md`. Built/refreshed at consolidate time,
  read cheaply at recall time; invalidated incrementally by file mtime;
  **a regenerable cache, never the source of truth** (delete it and it rebuilds).
  A `vectors` table is reserved for a future semantic retriever. Gitignore it.

See [`docs/aigg_memory_kernel_design.md`](docs/aigg_memory_kernel_design.md).

## Test

```bash
pip install -e ".[test]"
python -m pytest          # the kernel + markdown + typed-memory domains
```

The suite includes an **isolation invariant**: no `aigg_memory` source file may
import a host framework.

## License

Not yet chosen — see the parent project. Add a `LICENSE` before publishing.
