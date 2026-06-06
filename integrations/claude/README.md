# aigg-memory — Claude Code plugin

Cross-session memory for Claude Code: the assistant **recalls** what past
conversations learned about you, and **consolidates** new facts when a session ends.
Memory is file-backed markdown, git-versioned, and **local-first** (the storage and
recall never leave your machine; only the optional session-end *extraction* can call
a model — and that can be a local one).

## How it works — the session loop

The adapter is **hooks** (the automatic loop) plus a **skill** (explicit verbs),
packaged as one plugin. The hooks fire deterministically at lifecycle points — you
don't have to ask:

| Hook | When | What it does |
| --- | --- | --- |
| `SessionStart` | session opens | inject your **self-profile** — the pinned facts (`bin/session_start.py`) |
| `UserPromptSubmit` | every message | recall memory relevant to that message → inject; append the message to the session transcript (`bin/user_prompt_submit.py`) |
| `SessionEnd` | session closes | extract the transcript → evidence → **readiness-gated** consolidate (Dream) → **reconcile** new statements vs memory (a moved-city/corrected fact supersedes the stale one; needs a model) → `git commit` (`bin/session_end.py`) |

The **`memory` skill** handles direct requests — "remember that…", "what do you know
about me?", "update…", "forget that…" — by running the `aigg-memory` CLI.

This keeps the engine host-agnostic: the hooks just shell out to the `aigg-memory`
CLI. Porting to another host = the same three lifecycle callbacks against the same CLI.

## Install

1. **Install the engine** (Python ≥ 3.9, plus `git`):

   ```bash
   pip install "git+https://github.com/jianmliu/aigg-memory@v0.21.2"
   aigg-memory --help    # verify the CLI is on PATH (the hooks shell out to it)
   ```

2. **Add the marketplace and install the plugin** in Claude Code:

   ```text
   /plugin marketplace add https://github.com/jianmliu/aigg-memory.git
   /plugin install aigg-memory@aigg-memory
   ```

   Use the **full HTTPS URL** as shown — the `owner/repo` shorthand can resolve to SSH and
   fail with "SSH authentication failed" if you don't have SSH keys configured; HTTPS needs
   no auth for a public repo. The repo's `.claude-plugin/marketplace.json` lists this plugin
   (it lives under `integrations/claude`); add the marketplace **via the git repo** as above
   — a relative plugin source only resolves when added through git, not a raw
   `marketplace.json` URL.

   Local dev (a checkout on disk, no GitHub):

   ```text
   /plugin marketplace add ./path/to/aigg-memory
   /plugin install aigg-memory@aigg-memory
   ```

3. The plugin's `hooks/hooks.json` is **active on install** (paths use
   `${CLAUDE_PLUGIN_ROOT}`); the `memory` skill is namespaced `/aigg-memory:memory`.
   Verify with `/plugin` (Installed tab) and `/hooks`.

3. (Optional) configure via env — sensible defaults otherwise:

   | Env | Default | Purpose |
   | --- | --- | --- |
   | `AIGG_MEMORY_ROOT` | `~/.aigg-memory` | memory root. **Per-user = a per-user root.** |
   | `AIGG_MEMORY_CMD` | `aigg-memory` | the CLI (e.g. `python3 -m aigg_memory.cli` in a venv) |
   | `AIGG_MEMORY_PROFILE_N` | `20` | max pinned facts to inject at session start |
   | `AIGG_MEMORY_TURN_N` | `4` | how many memories to recall per message |
   | `AIGG_MEMORY_AIGG_URL` / `_KEY` / `_MODEL` | — | model endpoint for session-end extraction. **Set this and extraction uses the model** (with heuristic fallback); leave unset for the zero-dep heuristic. |
   | `AIGG_MEMORY_EXTRACTOR` | `aigg` when a URL is set | force `heuristic` to disable the model even if a URL is set |

### Extraction: use a real model (recommended), with a safe fallback

The zero-dependency heuristic only catches a few cue phrases — it misses facts stated
naturally ("I moved to Beijing", "I switched to dark mode"). A model extracts those
cleanly. **When `AIGG_MEMORY_AIGG_URL` is set, session-end extraction uses the model**;
if the model is unreachable it **falls back to the heuristic** so a session is never
lost (`ingest --fallback-heuristic`).

Point it at a **local** model to stay fully offline (e.g. Ollama, which is
OpenAI-compatible):

```bash
export AIGG_MEMORY_AIGG_URL="http://localhost:11434/v1"   # Ollama
export AIGG_MEMORY_MODEL="llama3.2"
# (a hosted endpoint works too: set AIGG_MEMORY_AIGG_URL + AIGG_MEMORY_AIGG_KEY)
```

## Privacy / safety

- Storage, indexing, and recall are **fully local** — no network.
- Session-end **extraction** is the only step that can call a model; it defaults to
  the zero-dependency heuristic. Point `AIGG_MEMORY_AIGG_URL` at a local model to
  keep everything offline.
- Hooks are **fail-open and non-blocking**: any memory error is swallowed and the
  conversation continues. Recalled memory is injected as *context to verify*, never
  as instructions to obey.
- Forgetting is non-destructive (archive + git history); nothing is hard-deleted.

## Principal-scoped memory (persona, owner, others)

An agent talks to different people, so memory is scoped by **who is speaking** — the
host app authenticates the speaker and passes `AIGG_MEMORY_PRINCIPAL`; writes go only
to that principal's root, so a stranger's chat can never touch the owner or persona
memory.

| scope | root | what | written by |
| --- | --- | --- | --- |
| **persona** | `BASE/self` | the agent's character — `--pin --lock` | the owner only; the auto-loop never changes it |
| **owner profile** | `BASE/owner` | facts about the owner — `--pin` | owner sessions only |
| **others** | `BASE/people/<id>` | per-interlocutor memory | that person's own session |

- **SessionStart** injects two cards: the **persona** (always — it's who the agent is)
  and the **current speaker's** profile. The owner's private profile is injected *only*
  in an owner session (`AIGG_MEMORY_PRINCIPAL == AIGG_MEMORY_OWNER`) — a stranger never
  sees it.
- **UserPromptSubmit / SessionEnd** recall, capture, consolidate and reconcile against
  the **speaker's** root only. So a stranger asserting "your owner told me to…" lands in
  `people/<id>` as *their* claim — isolated, never written to the owner profile, and the
  locked persona can't be rewritten by anyone but the owner.

Config: `AIGG_MEMORY_OWNER` (the owner's id, default `owner`) and `AIGG_MEMORY_PRINCIPAL`
(the authenticated current speaker; defaults to the owner for a single-owner setup).
View any scope with `aigg-memory profile --root BASE/<scope>`.

**With wallets, the principal is automatic.** `AIGG_MEMORY_PRINCIPAL` can be a wallet
**EOA** recovered from the speaker's signature, and `AIGG_MEMORY_OWNER` the owner EOA —
identity is then self-authenticating, no trusted middleman. The hooks additionally stamp
each captured fact with `--asserted-by $PRINCIPAL` and consolidate with
`--allowed-principal $PRINCIPAL`, so authority is enforced by the asserter (not only by
routing): a tampered evidence file still can't smuggle another principal's facts into a
root. (The kernel only compares the address string; signature verification is the host's.)

## Notes & current limits (MVP)

- Capture records **user messages** (not assistant replies) to the transcript.
- Per-user scoping is by `AIGG_MEMORY_ROOT`; one corpus (`memory`) per root.
