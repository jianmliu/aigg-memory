# `aigg-memory` — positioning & competitive landscape

> Where `aigg-memory` sits among the agent-memory products that emerged in
> 2025–2026, and what it deliberately does differently.
> Date: 2026-06-05.

## The category exists now

As of 2026, "agent memory" has graduated from a framework feature into its own
product category, on three tiers:

### 1. Dedicated memory layers (startups / OSS + managed cloud)

The tier `aigg-memory` is most often compared to.

| Product | Model | Primary use case |
| --- | --- | --- |
| **Mem0** | three scopes (user / session / agent); hybrid vector + graph + key-value store; managed cloud, SOC 2 / HIPAA | personalization (the de-facto default) |
| **Zep** | **temporal knowledge graph** (Graphiti) — tracks *when* a fact held and how entities relate over time | temporal reasoning |
| **Letta** (MemGPT lineage) | OS-inspired: in-context memory + external store + explicit **paging** | long-running agents |
| **LangMem** | LangChain-native memory SDK | LangChain stacks |
| Cognee, Supermemory, Memobase, Honcho, EverMind, … | assorted vector / graph / profile backends | various |

### 2. Hyperscaler managed memory (built into the agent runtime, GA late 2025)

- **AWS Bedrock AgentCore Memory** (preview 2025-07, GA 2025-10-13) — short-term
  working memory + long-term memory as a managed service.
- **Google Vertex AI Agent Engine — Memory Bank** — memory bundled into the
  managed runtime; long-term structured knowledge via BigQuery.
- **Azure AI Foundry Agent Service** — auto-extracts key info, scopes per
  authenticated user.

### 3. Consumer-product memory (built in, not sold separately)

- **OpenAI** — ChatGPT memory + **Dreaming** (offline consolidation).
- **Anthropic** — Claude's memory tool / context management.

## What they share — and where `aigg-memory` is orthogonal

The cloud services **validate the category**, but nearly all share one shape:
**managed, API-first, opaque store** (a vector or graph DB you query). The memory
is state inside someone else's black box; you don't own the substrate, can't `grep`
it, can't hand-edit it, and can't audit how it changed.

`aigg-memory` is the orthogonal path. Its differentiators are precisely the
properties an opaque managed store *cannot* offer:

| Dimension | Mainstream cloud memory | `aigg-memory` |
| --- | --- | --- |
| **Storage substrate** | opaque vector / graph DB | **plain `SKILL.md` files = source of truth** — grep-able, hand-editable |
| **Versioning / audit** | black-box state mutation | **git** `diff` / `log` / `restore` — every change auditable & revertible |
| **Deployment** | managed, vendor lock-in | **self-hosted, zero-dependency kernel** (PyYAML only); runs offline |
| **Typing** | mostly flat facts | one substrate, typed **procedural / semantic / episodic** |
| **Navigation** | API query only | **MemoryMakefile** dependency graph — a human sees *which* unit to edit and its blast radius |
| **LLM cost** | bundled into the service | **cost-aware**: cheap similarity pre-filters; the model judges only candidates; the confident case is auto-applied, the uncertain case is escalated to a human |

The derived artifacts (`.aimm-index.db`, `MemoryMakefile`, the `MEMORY.md` output)
are all regenerable caches; the markdown units are the only source of truth. That
inversion — **files own the truth, everything else is derived** — is what makes the
git model and hand-editing possible, and it is the thing the managed services
structurally cannot adopt.

## Feature parity & the one real gap

On the *operations* of a memory system, `aigg-memory` already covers what this tier
does: encode (extract from transcripts) → consolidate (Dream) → recall (semantic +
dependency-aware) → merge (unit-aware) → contradiction resolution → compaction →
a dependency graph. It additionally has git semantics and files-as-truth, which the
others don't.

What the others have *more* of:

- **Managed scale / ops** (Mem0, the hyperscalers) — multi-tenant hosting, SLAs,
  compliance. `aigg-memory` is a self-hosted library by design; this is a
  deployment choice, not a capability gap.
- **Temporal knowledge graph** (Zep) — but this is narrower than it first looks,
  because git already supplies one of the two temporal axes (see below).

### The temporal dimension is bi-temporal — and git owns the harder half

"Temporal memory" is two distinct axes, and conflating them overstates the gap:

- **Transaction time** — *when memory recorded or changed a belief.* `aigg-memory`
  gets this **for free from git**: `log` is the store's belief timeline (now stamped
  with each commit's ISO time), `git log --follow <unit>` is a single fact's
  change-history, and `restore(ref)` reconstructs the store *as it was known at any
  past point* — a native point-in-time / "what did we believe as of T" query. This
  is the harder, audit-heavy axis; Zep builds an engine for it, git gives it
  structurally, with full diff/revert.

- **Valid (world) time** — *when a fact was actually true in the world*, which is
  not the commit time (you can record a 2025 event in a 2026 commit). Git does **not**
  carry this; it belongs in unit frontmatter (`valid_from` / `valid_to` /
  `event_time`).

So the residual gap is not "temporal" writ large — it is the three pieces git's
transaction-time history can't express. All three are now **implemented**, each on
an existing extension point:

1. **Valid / world time** → frontmatter fields `valid_from` / `valid_to` (set via
   `edit`, carried through merge, indexed).
2. **Temporal *ordering* relations** ("A before B") → a directed `precedes` edge,
   built by the *same* AIGG machinery as `depends_on` (`infer-temporal`), validated
   against real slugs, navigable via `deps` (`preceded_by`).
3. **Indexed temporal retrieval** → a `valid_from` column in the derived index, with
   `timeline()` (world-time order) and `as_of(t)` (point-in-time) queries — the
   world-time complement to git's transaction-time `restore`.

What Zep still has beyond this is a fully *graph-native* temporal model (time-scoped
entity relations as first-class graph edges with automatic invalidation); `aigg-memory`
covers the same *queries* (when-true, ordering, as-of) on the file + index substrate.
The headline "no temporal graph" was an overstatement: git supplied the hard
transaction-time half for free, and these three additions close the world-time half.

## Deliberate non-goals

- **Decay / eviction.** At the realistic scale (a corpus is at most a few million
  words of markdown — about one novel, a few MB), storage is not the bottleneck;
  recall *precision* is, and that's handled by semantic + dependency-aware retrieval
  over the full set. Eviction solves a working-set-vs-unbounded-store tension that
  doesn't arise here, so it is out of scope by decision — not technical debt.
  (Letta's paging is the inverse bet: optimize the working set for very long runs.)

## One-line positioning

> The managed services give you memory **you rent and query**.
> `aigg-memory` gives you memory **you own, can read, can hand-edit, and can
> version like code** — a self-hosted, git-versioned, file-backed memory kernel,
> where the markdown is the truth and everything else is a regenerable cache.

## Sources

- [State of AI Agent Memory 2026 — Mem0](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- [AI agent memory systems in 2026: Zep, Mem0, Letta — Hermes OS](https://hermesos.cloud/blog/ai-agent-memory-systems)
- [Agent Memory at Scale 2026: Letta, Zep, Mem0, LangMem — AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/10/agent-memory-vendor-landscape-2026-letta-zep-mem0-langmem)
- [Amazon Bedrock AgentCore Memory — AWS](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-agentcore-memory-building-context-aware-agents/)
- [AWS Bedrock AgentCore vs Azure vs Vertex, Q2 2026 — AgentMarketCap](https://agentmarketcap.ai/blog/2026/04/09/aws-bedrock-agentcore-vs-azure-ai-agent-service-vs-google-vertex-ai-agents-q2-2026)
- [ChatGPT memory & Dreaming — OpenAI](https://openai.com/index/chatgpt-memory-dreaming/)
</content>
</invoke>
