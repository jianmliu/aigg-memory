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

**Any language, over HTTP.** aigg-memory ships its own server, so a TypeScript /
Go / etc. app calls it as a backend — no Python in the client:

```bash
aigg-memory serve --root ./game-memory --port 8788   # terminal 1
node examples/mud-demo.mjs                            # terminal 2 (Node 18+, no npm install)
```

`examples/mud-demo.mjs` runs the same NPC loop over `fetch`; `examples/mud-client.ts`
is a reusable typed client (one corpus per NPC: `npcs/<id>/memory`).

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
aigg-memory ingest --transcript chat.txt --evidence ev.jsonl --extractor aigg \
  --aigg-url http://localhost:11434/v1 --model llama3.2 --fallback-heuristic        # local model, degrade if down
```

The heuristic only catches a few cue phrases; a model extracts facts stated naturally
("I moved to Beijing") that the heuristic misses entirely. `--fallback-heuristic` makes
the model path safe to rely on — if the endpoint (e.g. a local Ollama) is unreachable,
it degrades to the heuristic instead of dropping the transcript. The endpoint can be
local, so extraction stays offline too.

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

### Serving it: safe-by-default, trusted-network scope

`serve` binds **`127.0.0.1` by default**, so out of the box it's a localhost
backend. Safe-by-default hardening is built in: the `corpus` path is validated on
every request (a `..` / absolute path is rejected, so it can't escape `root`;
nesting is still allowed), the optional `--token` is compared in constant time, and
oversize request bodies are refused.

```bash
aigg-memory serve --root . --token "$TOK"                 # localhost, authenticated
aigg-memory serve --root . --host 0.0.0.0 --token "$TOK"  # expose on a TRUSTED network, on purpose
```

This makes it a sound backend for **trusted clients on a trusted network** (its
intended use — a TS/Go app calling it). It is **not** meant to be exposed raw to the
public internet: there is no TLS, no rate limiting, no multi-tenant authorization,
and the AIGG-inference endpoints take `aigg_url` from the request body (an SSRF
vector for untrusted callers). For public exposure, put it behind a reverse proxy
that terminates TLS and handles auth / rate limiting, and keep the bind on
localhost. Binding `0.0.0.0` without a `--token` prints a warning.

## Integrations — cross-session memory for an AI assistant

`integrations/claude/` is a **Claude Code plugin**: the assistant recalls what past
conversations learned about you and consolidates new facts at session end. The
adapter is **hooks** (the automatic loop — `SessionStart` injects your profile,
`UserPromptSubmit` recalls per message, `SessionEnd` runs the Dream + `git commit`)
plus a **`memory` skill** (explicit "remember / what do you know / forget"). The
hooks just shell out to the `aigg-memory` CLI (`recall`, `consolidate-corpus`,
`commit`), so the engine stays host-agnostic — porting to another chat host is the
same three lifecycle callbacks. See [`integrations/claude/README.md`](integrations/claude/README.md).

The daemonless `recall` CLI makes this possible without a running server; the
**self-profile** is the pinned tier injected at every session start (identity +
durable preferences), vs memory recalled on demand:

```bash
aigg-memory recall "keep it brief" --root ~/.aigg-memory   # on-demand recall (mirrors /memory/select)
aigg-memory edit name_is_alex --root ~/.aigg-memory --pin  # add to the always-injected self-profile
aigg-memory profile --root ~/.aigg-memory                  # the self-profile (pinned units)
```

## Memory is versioned, not deleted (git)

The corpus is plain `<slug>/SKILL.md` text — so it is **directly git-versionable**.
Consolidation / compaction / edits become **commits**; nothing is destroyed. A
"forgotten" unit leaves HEAD (the active set) but stays in history and can be
restored. This is forgetting done right: bound the *working set*, keep the *store*
— and unlike a black box that mutates state irreversibly, every memory change is
**auditable and revertible**.

```bash
aigg-memory compact --write --commit          # folding duplicates is a recoverable commit
aigg-memory log                               # the memory history
aigg-memory diff --base HEAD~1 --head HEAD    # what a Dream/compaction changed (unit-level)
aigg-memory restore HEAD~1                     # bring a 'forgotten' unit back from history
```

`commit` / `log` / `diff` / `restore` are in `aigg_memory.versioning`; the derived
`.aimm-index.db` + `MemoryMakefile` are gitignored.

**Merging memory (shared / multi-agent).** `merge_corpora` / `merge_into` do a
*unit-aware* field-level merge — combine an NPC's personal memory with shared world
lore, or two agents' memory: units unique to a side are kept, a unit in both is
merged (union `match`/`source_events`/`deps`, max `observations`/`confidence`, newer
scalars, keep active over archived), and only a **genuine value conflict** (divergent
body / status) surfaces — `ours` is kept, `theirs` is reported — for a human or an
LLM to resolve. (Structural conflicts are deterministic; *contradiction* detection
between different units is the LLM's job — see below.)

```bash
aigg-memory merge --from ../shared-lore --write --commit   # field-merge; conflicts are reported, then committed
```

**Contradiction detection (semantic conflicts).** Two different units can assert
incompatible facts ("timeout is 30s" vs "60s") — embeddings can't tell that apart
from similarity (both are high-cosine). So `detect_contradictions` is cost-aware:
cheap semantic similarity narrows to same-topic *candidate* pairs, then an external
**AIGG** model judges which genuinely contradict and picks a winner; the loser is
**archived** (non-destructive, restorable) and the supersession recorded on the
winner. The LLM only ever sees the candidates.

**The model is allowed to be unsure — and never guesses.** A pair only auto-resolves
when the model confidently names a winner. If it genuinely contradicts but the model
can't tell *which* is correct (`winner: "uncertain"`, or an invalid pick), the pair
is **not** acted on — it lands in `needs_review` for a human to decide, and nothing
is archived. Guessing wrong here would delete a correct memory, so the safe default
is to escalate, not gamble. (Hallucinated *nodes* — ids that aren't real units — are
dropped outright.)

```bash
aigg-memory detect-contradictions --aigg-url https://aigg.example/v1 --write
# -> {"resolved": [...confident, archived...], "needs_review": [...ask a human...]}
```

**Keeping memory current — reconciling a new statement.** When a user says "I moved
to Beijing", the old "lives in Shanghai" shouldn't linger. `reconcile` is the directed
version of the above: cheap similarity narrows candidate pairs, then a model judges how
the pair relates and **which fact holds now**, and routes —

- **correction** (the old fact was *wrong*) → archive it, the current one supersedes it;
- **temporal** (the old fact was true *before*) → archive it **and stamp `valid_to`=now**,
  the current fact gets **`valid_from`=now** — non-destructive, so recall returns the
  current fact while `timeline` / `as_of` still answer "what was true *then*";
- **none** → leave both; **uncertain** → `needs_review`, never a guess.

```bash
aigg-memory reconcile --aigg-url https://aigg.example/v1 --now 2026-06-06 --write
# moved-city -> old archived+valid_to, new valid_from; recall returns the current fact,
# the timeline keeps the history. (The clock is the caller's: pass --now.)
```

**Two orthogonal flags — and the agent persona card.** `pinned` and `locked` answer
different questions:

| flag | question | learned user-fact | agent **persona card** |
| --- | --- | --- | --- |
| `pinned` | always injected? (the self-profile tier) | yes | yes |
| `locked` | protected from the **automatic** loop? | no (a moved city *should* auto-update) | **yes** |

For a human assistant, the profile is *learned* and auto-updates. For an **agent**, the
pinned profile is a **persona card (人设卡)**: authored by the **owner**, not learned —
so it must never be silently overwritten by what a conversation claims. `locked` enforces
that: `reconcile` and `detect-contradictions` will **never archive a locked unit** — a
genuine conflict against it goes to `needs_review` for the owner, who is the only one
who edits it. A persona card is `pinned + locked`; a learned fact is `pinned` only.

```bash
aigg-memory edit persona --lock     # owner-authored: the auto-loop won't touch it
```

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

**Where directed dependencies come from.** `depends_on` / `supersedes` are
*directed, causal* relations — embeddings can't infer them (cosine is symmetric
topic-overlap; a high-similarity pair is usually a near-duplicate, not a
prerequisite). So they're either hand-declared in frontmatter, or built by a model:

```bash
aigg-memory infer-deps --aigg-url https://aigg.example/v1 --write   # an AIGG model asserts the edges
```

The model reads the units and proposes directed edges; they are **validated against
real slugs** (no hallucinated nodes, no self-loops) before being written. The
inference call routes through **AIGG**, so it's cost-controlled by the same
per-task token budget. (Similarity stays in the retriever; the graph carries only
what similarity can't.)

**Dependency-aware recall.** The same graph powers recall: `select` /
`POST /memory/select` with `include_deps` appends a recalled unit's prerequisite
closure (its `depends_on` units, marked `relation: dependency`), so an agent that
recalls "budget" also gets the "token_concept" it depends on — the context is
complete. A consumer (e.g. AgentMakefile) reuses this; it never re-computes the
graph.

## Temporal memory — when a fact was *true*, and what came *before* what

Memory has two time axes, and **git already owns one**: the commit history is the
*transaction time* — `log` is the store's belief timeline, and `restore(ref)`
reconstructs memory *as it was known at any past point*. So the temporal layer only
adds the three things commit metadata can't express:

1. **Valid / world time** — *when a fact was true*, not when it was recorded (a 2025
   event can be committed in 2026). It lives in the unit's frontmatter
   (`valid_from` / `valid_to`), set on consolidation, extraction, or by hand:

   ```bash
   aigg-memory edit reorg --valid-from 2025-01-01 --valid-to 2025-03-01
   ```

2. **Temporal ordering** — *A happened before B*. This is world-time semantics, not
   commit order, so (exactly like `depends_on`) it's a directed `precedes` edge,
   built by the **same** AIGG machinery as `infer-deps` and validated against real
   slugs:

   ```bash
   aigg-memory infer-temporal --aigg-url https://aigg.example/v1 --write
   aigg-memory deps promo     # -> "preceded_by": ["reorg"]  (alongside depends_on / supersedes)
   ```

3. **Indexed temporal retrieval** — git can *reconstruct* a timeline by walking
   history but can't *index* it. The derived index gets a `valid_from` column, so
   the timeline / point-in-time query is a cheap lookup:

   ```bash
   aigg-memory timeline                       # units ordered by world-time
   aigg-memory timeline --as-of 2025-02-01    # only facts true at that moment
   ```

   `as_of` is the world-time complement to git's transaction-time `restore`: one
   answers "what was *true* then," the other "what did we *know* then."

`POST /memory/infer-temporal` and `POST /memory/timeline` expose the same.

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

See [`docs/aigg_memory_kernel_design.md`](docs/aigg_memory_kernel_design.md). For how
this compares to managed agent-memory services (Mem0 / Zep / Letta, AWS AgentCore,
Vertex Memory Bank) and what it deliberately does differently, see
[`docs/positioning.md`](docs/positioning.md).

## Test

```bash
pip install -e ".[test]"
python -m pytest          # the kernel + markdown + typed-memory domains
```

The suite includes an **isolation invariant**: no `aigg_memory` source file may
import a host framework.

## License

Not yet chosen — see the parent project. Add a `LICENSE` before publishing.
