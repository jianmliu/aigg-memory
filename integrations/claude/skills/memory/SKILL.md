---
name: memory
description: >-
  Explicitly manage what the assistant remembers about the user across
  conversations (aigg-memory). Use when the user says things like "remember
  that…", "save this", "what do you know/remember about me?", "update what you
  know about…", "forget that…", or asks to see/edit their stored memory. For the
  automatic per-session recall/consolidation, the plugin's hooks handle it — this
  skill is for direct, user-invoked memory actions.
---

# Managing user memory (aigg-memory)

The user's cross-session memory lives under `$AIGG_MEMORY_ROOT` (default
`~/.aigg-memory`) as markdown units, managed by the `aigg-memory` CLI. Run these
with the Bash tool. Memory is git-versioned, so nothing is ever truly lost.

Set `ROOT="${AIGG_MEMORY_ROOT:-$HOME/.aigg-memory}"` for the commands below.

## "Remember that X" / "Save this"

Record it as an observation, then consolidate so it becomes a durable unit. Choose
a stable snake_case `slug`, a `kind` (`semantic` for facts/preferences,
`procedural` for how-to, `episodic` for events), and a few `match` trigger phrases.

```bash
aigg-memory remember --evidence "$ROOT/evidence.jsonl" --json '{
  "slug": "prefers_metric_units", "name": "prefers_metric_units", "kind": "semantic",
  "description": "User prefers metric units", "match": ["units", "metric", "measurements"],
  "body": "User prefers metric (SI) units in answers."}'
aigg-memory consolidate-corpus --root "$ROOT" --evidence "$ROOT/evidence.jsonl" --write --min-count 1
aigg-memory commit --root "$ROOT" --message "remember: prefers_metric_units"
```

An explicit "remember that…" is high-confidence — pass `--min-count 1` so it lands
**immediately** (the automatic session-end loop keeps the default repetition gate of
2, so one-off chatter isn't promoted; an explicit instruction shouldn't wait).

### Pin core identity/preferences to the profile

The **self-profile** is the small set of pinned facts injected at the start of *every*
session (name, role, durable preferences) — vs ordinary memory that's recalled only
when relevant. When a fact is core "about me", pin it:

```bash
aigg-memory edit <slug> --root "$ROOT" --pin       # add to the always-injected profile
aigg-memory edit <slug> --root "$ROOT" --unpin     # demote back to on-demand recall
aigg-memory profile --root "$ROOT"                  # see the current self-profile
```

Pin identity and stable preferences (name, language, communication style, ongoing
projects); leave one-off or episodic facts unpinned.

## "What do you know / remember about me?"

Recall against the topic, or list everything. Present the descriptions plainly.

```bash
aigg-memory recall "preferences identity projects" --root "$ROOT" --n-best 20
```

## "Update what you know about X" (a fact changed)

The user's facts change ("I moved", "I switched jobs"). Edit the unit; for genuine
contradictions you can also set world-time validity so the timeline stays correct.

```bash
aigg-memory edit <slug> --root "$ROOT" --description "New value" --valid-from 2026-06-01
aigg-memory commit --root "$ROOT" --message "update: <slug>"
```

To let a model reconcile contradictions across units (confident → supersede,
uncertain → it asks you):

```bash
aigg-memory detect-contradictions --root "$ROOT" --aigg-url "$AIGG_URL" --write
```

## "Forget that X"

Forgetting is non-destructive — archive the unit (it leaves the active set but stays
in git history and can be restored).

```bash
aigg-memory edit <slug> --root "$ROOT" --status archived
aigg-memory commit --root "$ROOT" --message "forget: <slug>"
```

To truly review history / bring something back: `aigg-memory log --root "$ROOT"` and
`aigg-memory restore <ref> --root "$ROOT"`.

## Notes

- Find a unit's slug from a `recall` result (the `slug` field) before editing.
- Everything is local markdown under `$ROOT/memory/<slug>/SKILL.md` — the user can
  also open and hand-edit it. The index rebuilds itself.
