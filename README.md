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

## Install

```bash
pip install aigg-memory          # once published
pip install -e .                 # from a checkout
```

Only runtime dependency: PyYAML (for SKILL.md frontmatter). The kernel core
(`models` / `store` / `kernel` / `_util`) is dependency-free.

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
