# aigg-memory — Quickstart

Long-term memory for an AI agent: it remembers what past conversations learned about
you, and keeps that memory current as you talk. Share this page to get someone up and
running in a few minutes.

## What it is

- **Yours, readable, editable** — memory is local **markdown files**, not state inside a
  black box. You can `grep` it, hand-edit it, `git diff` it.
- **Git-versioned** — every change to memory is a commit: auditable, revertible;
  "forgetting" is archiving, never deletion.
- **Local-first** — storage, recall and consolidation all run on your machine, with one
  dependency (PyYAML). Even the LLM extraction can point at a local model.
- **Updates, doesn't pile up** — a new statement reconciles old memory (you moved → the
  old address becomes *past*, not a contradiction; you corrected something → it's fixed).
  Anything the model can't decide is left for a human — it never guesses.
- **Scoped & authorized** — an agent persona card (owner-set, conversations can't change
  it), an owner profile, and a separate isolated memory per other person. Wallet (EOA)
  identity and signed provenance fit in natively.
- **DSN-ready** — can sync to decentralized storage (Autonomys Auto Drive): encrypted,
  permanent, and carrying the full git history (not a flat snapshot).

## Install

### 1. The engine (required) — Python ≥ 3.9 and `git`

```bash
pip install "git+https://github.com/jianmliu/aigg-memory@v0.21.3"
aigg-memory --help      # confirm the CLI is on PATH
```

### 2. The Claude Code plugin (cross-session memory)

In a normal Claude Code session, run these **one at a time** (not pasted together):

```text
/plugin marketplace add https://github.com/jianmliu/aigg-memory.git
```

then, once it has cloned:

```text
/plugin install aigg-memory@aigg-memory
```

> Use the full **HTTPS** URL shown — the `owner/repo` shorthand can resolve to SSH and
> fail with "SSH authentication failed". Don't paste both lines at once (they'd merge
> into one malformed URL).

## Verify it works

### A. The engine, standalone (any empty dir, fully offline)

```bash
mkdir /tmp/m && cd /tmp/m
aigg-memory remember --evidence ev.jsonl --json '{"slug":"likes_metric","name":"likes_metric","kind":"semantic","description":"User prefers metric units","match":["units","metric"],"body":"metric"}'
aigg-memory consolidate-corpus --root . --evidence ev.jsonl --write --min-count 1
aigg-memory recall "what units do they use" --root .
```

✅ The recall output contains `"description": "User prefers metric units"` → the engine works.

### B. The plugin is loaded (in Claude Code)

```text
/plugin     → the Installed tab lists "aigg-memory"
/hooks      → shows SessionStart / UserPromptSubmit / SessionEnd
```

### C. End-to-end (memory across sessions)

1. In Claude, say: **"Remember that I prefer metric units."**
2. In a terminal, confirm the memory landed on disk:
   ```bash
   find ~/.aigg-memory -name SKILL.md
   ```
   ✅ A new `SKILL.md` appears → hook + skill + engine are wired together.
3. Open a **new** Claude session and ask: **"What do you remember about my preferences?"**
   ✅ It answers "metric units" → cross-session memory is working.

## License

[MIT](LICENSE). Source: <https://github.com/jianmliu/aigg-memory>
