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

A unit carries more than the bare fact, so recall is directly *usable*: an **`apply`**
field — one line of actionable guidance ("default to dark mode when a UI choice is open")
surfaced alongside the fact on recall; **`origin_session`** — which conversation it came
from (provenance, beside `asserted_by`/`source_events`); and **readable slugs**
(`prefers_dark_mode`, not `fact_3a9f…`) so units stay hand-editable. Set with
`aigg-memory edit <slug> --apply "…"`, or the model fills `apply` during extraction.

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

`examples/mud-demo.mjs` runs **two NPCs**, each with its own memory + **dream**, over
`fetch` — each NPC `observe`s, `dream`s on its own sleep trigger, and `recall`s only its
own memory (isolated by corpus). `examples/mud-client.ts` is a reusable typed client
(one corpus per NPC: `npcs/<id>/memory`; `sleep()` fires `/memory/dream`).

## Install

Requires **Python ≥ 3.9** and **git** (the versioning / `bundle` / `restore` features
shell out to it). Not on PyPI yet — install from GitHub:

```bash
pip install "git+https://github.com/jianmliu/aigg-memory@v0.21.2"   # pin a release (recommended)
pip install "git+https://github.com/jianmliu/aigg-memory@main"      # or latest
```

From a checkout (to hack on it / run the tests):

```bash
git clone https://github.com/jianmliu/aigg-memory && cd aigg-memory
pip install -e .                 # editable install
pip install -e ".[test]" && python -m pytest    # with the test deps
```

As a dependency of another project (`pyproject.toml` / `requirements.txt`):

```
aigg-memory @ git+https://github.com/jianmliu/aigg-memory@v0.21.2
```

The only runtime dependency is **PyYAML** (for SKILL.md frontmatter); the kernel core
(`models` / `store` / `kernel` / `_util`) is dependency-free. Verify with
`aigg-memory --help`.

```bash
pip install "aigg-memory[embedding] @ git+https://github.com/jianmliu/aigg-memory@v0.21.2"
# optional: real semantic embeddings (sentence-transformers + torch). The default
# zero-dependency HashEmbedder already works, so this is opt-in.
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

**Three inference backends.** Every model-using command (`ingest`, `dream`, `reconcile`,
`curate`, `reflect`, `plan`, `infer-deps`, …) takes `--backend`:

- **`http`** (default) — POST to any OpenAI-compatible `/chat/completions`: a local Ollama
  (offline, no key) or Anthropic's OpenAI-compat endpoint (`--aigg-url
  https://api.anthropic.com/v1 --aigg-key sk-ant-…`).
- **`claude-cli`** — shells out to **`claude -p`** (Claude Code headless), so it **reuses
  your Claude Code login (subscription, no API key)**; no `--aigg-url` needed. Crypto/auth
  stay in Claude Code; the kernel just runs the subprocess.

```bash
aigg-memory dream --evidence ev.jsonl --write --backend claude-cli        # uses `claude -p`
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
POST /memory/dream                 the full offline pass (consolidate + reconcile, + deep: compact/curate/reflect/plan)
POST /memory/reflect               synthesize beliefs from fact clusters (the backward synthesis layer)
POST /memory/plan                  synthesize forward intentions from goals+beliefs (the forward layer)
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

### Storing on a DSN (e.g. Autonomys Auto Drive)

Memory is **git-format**, so the bundle is a **`git bundle`** — the whole versioned repo
(all of `log` / `diff` / `restore`, the audit trail), **not** a flattened snapshot — packed
into one binary object. So the *versioned* memory round-trips through a single object on a
decentralized store. The kernel stays **crypto-free**: a store like **Auto Drive** encrypts
the bytes client-side on upload (a password derived from the owner's key), so the host just
pipes the bundle through its encrypted put/get — the DSN sees only ciphertext, the kernel
only plaintext.

```bash
aigg-memory bundle export --root ~/.aigg-memory/owner | autodrive-put --password "$KEY"   # -> CID
autodrive-get "$CID" --password "$KEY" | aigg-memory bundle import --root ./restored
# the restored corpus has the FULL history: `aigg-memory log/diff/restore` all work
```

Recall still happens **locally** (download → decrypt → rebuild the index → recall): the DSN
is cold storage / sync, never a query layer. Because it carries git, sync can be
**incremental** (bundle only commits since a known ref). Identity + provenance
(`asserted_by`, an EOA) pair naturally with Auto ID; permanence means "forgetting" is
access-based (rotate keys), and ciphertext is immutable — anyone who held a key can still
read old versions.

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
that across **every** automatic path — consolidation (correction / obsolete), compaction,
corpus merge, `reconcile`, and `detect-contradictions` all **refuse to modify or archive a
locked unit**; a genuine conflict against it goes to `needs_review` for the owner, who is
the only one who edits it (`edit` is the owner's escape hatch). A persona card is
`pinned + locked`; a learned fact is `pinned` only.

```bash
aigg-memory edit persona --lock     # owner-authored: the auto-loop won't touch it
```

**Provenance & authority — `asserted_by`.** Each fact can record **who asserted it** —
a principal id, e.g. a wallet **EOA** address. It's just a string: the kernel stays
crypto-free; any signature verification happens in the host, which passes the recovered
address. Provenance flows from the observation to the unit (`ingest --asserted-by`,
`remember --asserted-by`), and it's an **authority gate**: a corpus can consolidate facts
*only* from an allowed asserter, so authority is enforced by the signer, not just by which
root a write was routed to.

```bash
aigg-memory ingest --transcript chat.txt --evidence ev.jsonl --asserted-by 0xSPEAKER
aigg-memory consolidate-corpus --root owner/ --evidence ev.jsonl --write --allowed-principal 0xOWNER
# a stranger's signed claim in the same evidence is dropped — only 0xOWNER writes the owner profile
```

With wallets this is automatic: agent / owner / passerby each have an EOA, identity is
recovered from a signature (no trusted middleman), and `asserted_by` makes a fact's
authority *verifiable* — though note provenance proves *who said it*, not that it's true.

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

## Curation — LLM value-triage of *unique* noise

Compaction merges *duplicates* (similarity, model-free). But it can't touch a **unique**
low-value unit — a one-off bit of chatter that resembles nothing else. Judging "is this
worth keeping?" for a unique fact is **semantic** (like contradiction / dependency):
statistics measure access or structure, not *worth* — a rarely-recalled fact may be
important, and a noise item is also rarely recalled. So this needs a model.

`curate` is cost-aware and conservative: a cheap structural filter narrows *candidates*
(active, **not** pinned/locked, **not** load-bearing), an AIGG model judges each
`keep` / `trivial` / `uncertain`, and only **high-confidence `trivial`** is archived —
non-destructively (git keeps it), erring toward keeping (deleting useful memory is worse
than keeping a little noise). `uncertain` and `keep` are left alone; a persona card or
profile (pinned / locked) is never even a candidate.

```bash
aigg-memory curate --aigg-url https://aigg.example/v1                       # dry-run: what looks trivial
aigg-memory curate --aigg-url https://aigg.example/v1 --kinds episodic --write   # archive the clear chatter
```

Together they cover the whole "tidy up" story: the consolidation **gate** keeps most
one-off chatter out; **compaction** folds duplicates; **curate** triages unique noise;
**reconcile** supersedes the stale. `POST /memory/curate` exposes the same.

## Dream — the offline maintenance pass

`dream` runs the offline maintenance as **one orchestrated call**, in two cadences:

- **Light** (every pass): consolidate new evidence into units, then reconcile new
  statements against memory. Fits every session end.
- **Deep** (`--deep`, periodic): also compact duplicates, curate unique noise, **reflect**
  (synthesize higher-level beliefs from the facts, `kind=belief`), then — with `--now` —
  **plan** (synthesize forward intentions from goals+beliefs, `kind=plan`). Heavier (an LLM
  pass over the corpus) — run it occasionally, not every time.

```bash
aigg-memory dream --evidence ev.jsonl --write --commit                       # light
aigg-memory dream --evidence ev.jsonl --write --commit --deep \
  --aigg-url http://localhost:11434/v1                                        # + periodic deep clean
```

The **trigger and cadence are the app's** — the engine ships no scheduler, only the
`consolidation-status` readiness signal. The LLM steps (reconcile / curate) run only when
`--aigg-url` is given; without a model, dream is just consolidation. In the Claude Code
plugin, `SessionEnd` calls `dream` (light) when there's new evidence, and adds `--deep`
every Nth session (`AIGG_MEMORY_DEEP_EVERY`, default 10).

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
[`docs/positioning.md`](docs/positioning.md). For the **Reflection** layer (from facts to
beliefs — the synthesis pass above Dream, riding the MemoryMakefile graph; MVP shipped:
`aigg-memory reflect`, `POST /memory/reflect`, and the Dream deep pass), see
[`docs/reflection_design.md`](docs/reflection_design.md). For the **Planning** layer (its
forward mirror — from beliefs+goals to intentions, reusing the same graph + stale-propagation
+ valid-time; MVP shipped: `aigg-memory plan`, `POST /memory/plan`, and the Dream deep pass;
action stays out of the kernel), see [`docs/planning_design.md`](docs/planning_design.md).
For the **behavioral evaluation** — reproducing Generative Agents' three emergent behaviors
(information diffusion, relationship formation, coordination) with aigg-memory as a MUD's
memory substrate, measured directly from the git-versioned corpora — see
[`docs/mud_emergence_eval.md`](docs/mud_emergence_eval.md), expressed in the extensible
experiment framework (shared runner / read-only probes / reusable verbs / pluggable world
adapters, so the N-th experiment is a manifest not a script) in
[`docs/experiment_harness.md`](docs/experiment_harness.md) — with a runnable MVP in
[`examples/eval/`](examples/eval/). The MUD itself is a **configurable sandbox** (reusable
rails + experiments-by-configuration, the same rig serving as product and lab) — see
[`docs/mud_sandbox_design.md`](docs/mud_sandbox_design.md). For the **research program** that
composes the emergences with an Effort-Luck-Choice economy (a superset of Pluchino's
Talent-vs-Luck) to ask whether memory lets talent reclaim success from luck — and the
markets/reflexivity extension where the headline result is *memory as anti-manipulation
immunity* (simulation only) — see
[`docs/memory_economy_research.md`](docs/memory_economy_research.md).

## Test

```bash
pip install -e ".[test]"
python -m pytest          # the kernel + markdown + typed-memory domains
```

The suite includes an **isolation invariant**: no `aigg_memory` source file may
import a host framework.

## License

[MIT](LICENSE) © 2026 Jianming Liu.
