#!/usr/bin/env python3
"""Import Claude Code's native auto-memory into aigg-memory.

Claude Code keeps a per-project auto-memory under ~/.claude/projects/<dir>/memory/*.md
(markdown + frontmatter). Those facts are already distilled — this reads them, maps each
to an aigg observation, and feeds the EXISTING `remember` + `consolidate-corpus` CLI, so
aigg layers git versioning, a cross-project owner profile, curation, and portability on
top of Claude's per-project extraction.

Pure integration layer: the Claude-specific paths + frontmatter schema live here; the
kernel is untouched (no Claude knowledge in it). Stdlib-only (a tiny frontmatter parser),
so it runs under whatever python3 the hook uses.

Mapping: filename -> readable slug; frontmatter name/description -> name/description;
a "**How to apply:** …" section in the body -> aigg's `apply` field; metadata
.originSessionId -> `origin_session`; asserted_by = the owner. Imported into BASE/owner.

Usage:  python3 import_native_memory.py [--from DIR]
        (default: every ~/.claude/projects/*/memory directory)
"""
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _aigg import OWNER, OWNER_ROOT, evidence_path, run_cli  # noqa: E402


def _parse_frontmatter(md):
    """Minimal stdlib frontmatter parse -> (frontmatter dict, body). Handles top-level
    `key: value` and one level of nesting (the `metadata:` block Claude uses)."""
    if not md.startswith("---"):
        return {}, md
    parts = md.split("---", 2)
    if len(parts) < 3:
        return {}, md
    head, body = parts[1], parts[2].lstrip("\n")
    fm, cur = {}, None
    for line in head.splitlines():
        if not line.strip():
            continue
        if re.match(r"^\S+\s*:", line):                  # top-level key
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip()
            if v == "":
                cur = k
                fm[k] = {}
            else:
                fm[k] = v
                cur = None
        elif cur and re.match(r"^\s+\S+\s*:", line):     # nested under the last key
            k, _, v = line.strip().partition(":")
            if isinstance(fm.get(cur), dict):
                fm[cur][k.strip()] = v.strip()
    return fm, body


def _observation(path, fm, body):
    stem = os.path.splitext(os.path.basename(path))[0]
    slug = re.sub(r"[^a-z0-9_]", "_", stem.lower().replace("-", "_")).strip("_") or "fact"
    name = fm.get("name") or slug
    # split a "**How to apply:** …" section out of the body into aigg's `apply` field
    apply = ""
    m = re.search(r"\*\*How to apply:\*\*\s*(.+)", body, re.S)
    if m:
        apply = re.split(r"\n\s*\n|Related:", m.group(1))[0].strip()
        body = body[:m.start()].strip()
    desc = fm.get("description") or (body.strip().split("\n")[0][:120] if body.strip() else name)
    meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
    obs = {
        "slug": slug, "name": name, "kind": "semantic", "description": desc,
        "match": [w for w in re.split(r"[_\s-]+", slug) if len(w) > 2][:5] or [slug],
        "body": body.strip() or desc, "asserted_by": OWNER,
    }
    if apply:
        obs["apply"] = apply
    osid = meta.get("originSessionId") or meta.get("origin_session_id")
    if osid:
        obs["origin_session"] = osid
    return obs


def main():
    src = sys.argv[sys.argv.index("--from") + 1] if "--from" in sys.argv else None
    dirs = [src] if src else sorted(glob.glob(os.path.expanduser("~/.claude/projects/*/memory")))
    ev = evidence_path(OWNER_ROOT)
    os.makedirs(os.path.dirname(ev), exist_ok=True)
    imported = []
    for d in dirs:
        for f in sorted(glob.glob(os.path.join(d, "*.md"))):
            if os.path.basename(f).upper() == "MEMORY.MD":   # the rollup index, not a unit
                continue
            try:
                fm, body = _parse_frontmatter(open(f, encoding="utf-8").read())
                obs = _observation(f, fm, body)
                run_cli(["remember", "--evidence", ev, "--json", json.dumps(obs, ensure_ascii=False)])
                imported.append(obs["slug"])
            except Exception as exc:
                sys.stderr.write(f"aigg-memory import: skip {f}: {exc}\n")
    if imported:
        # already-distilled facts -> promote immediately (min-count 1), then version
        run_cli(["consolidate-corpus", "--root", OWNER_ROOT, "--evidence", ev, "--write", "--min-count", "1"])
        run_cli(["commit", "--root", OWNER_ROOT, "--message",
                 f"import {len(imported)} fact(s) from Claude native auto-memory"])
    print(json.dumps({"imported": len(imported), "slugs": imported,
                      "into": OWNER_ROOT, "scanned": dirs}, ensure_ascii=False))


if __name__ == "__main__":
    main()
