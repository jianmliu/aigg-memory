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
| `SessionEnd` | session closes | extract the transcript → evidence → **readiness-gated** consolidate (Dream) → `git commit` (`bin/session_end.py`) |

The **`memory` skill** handles direct requests — "remember that…", "what do you know
about me?", "update…", "forget that…" — by running the `aigg-memory` CLI.

This keeps the engine host-agnostic: the hooks just shell out to the `aigg-memory`
CLI. Porting to another host = the same three lifecycle callbacks against the same CLI.

## Install

1. Install the engine (Python ≥ 3.9):

   ```bash
   pip install aigg-memory          # or: pip install git+https://github.com/jianmliu/aigg-memory
   ```

2. Add this plugin to Claude Code (it lives in the aigg-memory repo under
   `integrations/claude`). Its `hooks/hooks.json` is enabled on install; paths use
   `${CLAUDE_PLUGIN_ROOT}`.

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

## The self-profile

Session start injects your **self-profile** — the units explicitly pinned with
`aigg-memory edit <slug> --pin` (the `memory` skill does this for core identity facts).
It's the always-relevant tier: name, language, communication style, ongoing projects.
Everything else stays unpinned and is recalled only when a message makes it relevant.
View it any time with `aigg-memory profile`.

## Notes & current limits (MVP)

- Capture records **user messages** (not assistant replies) to the transcript.
- Per-user scoping is by `AIGG_MEMORY_ROOT`; one corpus (`memory`) per root.
