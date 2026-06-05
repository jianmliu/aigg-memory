"""A thin CLI for the agent-memory tools.

Flat markdown index:
    python -m aigg_memory observe    --evidence E.jsonl --json '{...}' [--outcome correction]
    python -m aigg_memory consolidate --memory MEMORY.md --evidence E.jsonl [--write]

Typed unit corpus (memory/<slug>/SKILL.md):
    python -m aigg_memory remember          --evidence E.jsonl --json '{"slug":..,"kind":..,..}' [--outcome correction|obsolete]
    python -m aigg_memory consolidate-corpus --root DIR --evidence E.jsonl [--write]

No agentmf import.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from aigg_memory.markdown import consolidate, markdown_memory_domain
from aigg_memory.memory import (
    build_memorymakefile,
    compact_corpus,
    consolidate_corpus,
    consolidation_status,
    edit_unit,
    memory_domain,
)
from aigg_memory.store import EvidenceStore

DEFAULT_MEMORY = "# Memory\n"


def _load_records(evidence_path: str) -> List:
    return EvidenceStore(evidence_path, domain=markdown_memory_domain()).load()


def consolidate_command(memory_path: str, evidence_path: str, write: bool = False) -> Dict[str, Any]:
    """Run consolidation; optionally write back when every gate passes.
    Returns a structured result (the testable core of the CLI)."""
    path = Path(memory_path)
    memory_text = path.read_text(encoding="utf-8") if path.exists() else DEFAULT_MEMORY
    result = consolidate(memory_text, _load_records(evidence_path))
    written = False
    if write and result.gates_ok and result.new_text != memory_text:
        path.write_text(result.new_text, encoding="utf-8")
        written = True
    return {
        "proposals": [p.to_dict() for p in result.proposals],
        "diff": result.patch.diff,
        "gates": [{"name": g.name, "passed": g.passed, "detail": g.detail} for g in result.gates],
        "gates_ok": result.gates_ok,
        "diagnostics": result.patch.diagnostics.to_list(),
        "new_text": result.new_text,
        "written": written,
    }


def observe_command(evidence_path: str, source: str, payload: Dict[str, Any], outcome: Optional[str] = None) -> Dict[str, Any]:
    store = EvidenceStore(evidence_path, domain=markdown_memory_domain())
    record = store.record(source, payload, outcome=outcome)
    return record.to_dict()


def remember_command(evidence_path: str, payload: Dict[str, Any], outcome: Optional[str] = None) -> Dict[str, Any]:
    """Record an observation for the typed unit corpus (memory-domain summary
    keeps slug/name/kind/description/match/body)."""
    store = EvidenceStore(evidence_path, domain=memory_domain())
    record = store.record("observation", payload, outcome=outcome)
    return record.to_dict()


def consolidate_corpus_command(root: str, evidence_path: str, write: bool = False) -> Dict[str, Any]:
    result = consolidate_corpus(root, _load_records(evidence_path), write=write)
    consolidation = result.consolidation
    return {
        "proposals": [p.to_dict() for p in consolidation.proposals],
        "diffs": consolidation.patch.diffs,
        "gates": [{"name": g.name, "passed": g.passed, "detail": g.detail} for g in consolidation.gates],
        "gates_ok": result.gates_ok,
        "written": result.written,
        "removed": result.removed,
    }


def consolidation_status_command(root: str, evidence_path: str, corpus: str = "memory", min_new: int = 1) -> Dict[str, Any]:
    return consolidation_status(root, _load_records(evidence_path), corpus=corpus, min_new=min_new).to_dict()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="aigg_memory", description="markdown agent-memory consolidation")
    sub = parser.add_subparsers(dest="command", required=True)

    observe = sub.add_parser("observe", help="append an observation to the evidence store")
    observe.add_argument("--evidence", required=True)
    observe.add_argument("--source", default="observation")
    observe.add_argument("--json", required=True, dest="payload_json", help="observation payload as JSON")
    observe.add_argument("--outcome", choices=["correction", "obsolete"], default=None)

    cons = sub.add_parser("consolidate", help="consolidate evidence into the memory index")
    cons.add_argument("--memory", required=True)
    cons.add_argument("--evidence", required=True)
    cons.add_argument("--write", action="store_true", help="write back when all gates pass")
    cons.add_argument("--format", choices=["text", "json"], default="text")

    remember = sub.add_parser("remember", help="record an observation for the typed unit corpus")
    remember.add_argument("--evidence", required=True)
    remember.add_argument("--json", required=True, dest="payload_json", help="observation payload as JSON")
    remember.add_argument("--outcome", choices=["correction", "obsolete"], default=None)

    corpus = sub.add_parser("consolidate-corpus", help="consolidate evidence into memory/<slug>/SKILL.md units")
    corpus.add_argument("--root", default=".", help="project root containing the memory/ directory")
    corpus.add_argument("--evidence", required=True)
    corpus.add_argument("--write", action="store_true", help="write changed units when all gates pass")
    corpus.add_argument("--format", choices=["text", "json"], default="text")

    status = sub.add_parser("consolidation-status", help="readiness signal: how much evidence is pending consolidation")
    status.add_argument("--root", default=".")
    status.add_argument("--evidence", required=True)
    status.add_argument("--corpus", default="memory")
    status.add_argument("--min-new", type=int, default=1, dest="min_new")

    serve = sub.add_parser("serve", help="run the local JSON memory API + web UI")
    serve.add_argument("--root", default=".", help="project root holding the corpus + evidence")
    serve.add_argument("--port", type=int, default=8788)
    serve.add_argument("--token", default=None, help="optional bearer token required on every request")

    graph = sub.add_parser("graph", help="compile the MemoryMakefile (dependency graph) for navigation")
    graph.add_argument("--root", default=".")
    graph.add_argument("--corpus", default="memory")
    graph.add_argument("--write", action="store_true", help="also write <corpus>/MemoryMakefile")

    deps = sub.add_parser("deps", help="show a unit's dependencies + blast radius (who depends on it)")
    deps.add_argument("slug")
    deps.add_argument("--root", default=".")
    deps.add_argument("--corpus", default="memory")

    edit = sub.add_parser("edit", help="update one memory unit (the source of truth)")
    edit.add_argument("slug")
    edit.add_argument("--root", default=".")
    edit.add_argument("--corpus", default="memory")
    edit.add_argument("--body")
    edit.add_argument("--description")
    edit.add_argument("--status", choices=["active", "candidate", "archived"], default=None)

    compact = sub.add_parser("compact", help="merge near-duplicate units (defrag / remove redundancy)")
    compact.add_argument("--root", default=".")
    compact.add_argument("--corpus", default="memory")
    compact.add_argument("--threshold", type=float, default=0.85, help="similarity threshold (higher = more conservative)")
    compact.add_argument("--write", action="store_true", help="apply the merges (default: dry-run)")

    args = parser.parse_args(argv)

    if args.command == "compact":
        result = compact_corpus(args.root, corpus=args.corpus, threshold=args.threshold, write=args.write)
        print(json.dumps({"merged": result.merged, "written": result.written, "removed": result.removed},
                         ensure_ascii=False, indent=2))
        return 0

    if args.command == "graph":
        print(json.dumps(build_memorymakefile(args.root, corpus=args.corpus, write=args.write),
                         ensure_ascii=False, indent=2))
        return 0

    if args.command == "deps":
        from aigg_memory.index import CorpusIndex
        idx = CorpusIndex(args.root, args.corpus)
        idx.sync()
        print(json.dumps({"slug": args.slug, "depends_on": idx.depends_on(args.slug),
                          "depended_by": idx.depended_by(args.slug), "supersedes": idx.supersedes(args.slug)},
                         ensure_ascii=False, indent=2))
        return 0

    if args.command == "edit":
        out = edit_unit(args.root, args.corpus, args.slug, body=args.body,
                        description=args.description, status=args.status)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out["updated"] else 1

    if args.command == "serve":
        from aigg_memory.server import run_server
        print(f"aigg-memory serve — root={args.root} http://127.0.0.1:{args.port}", file=sys.stderr)
        try:
            run_server(args.root, port=args.port, token=args.token)
        except KeyboardInterrupt:
            return 0
        return 0

    if args.command == "consolidation-status":
        print(json.dumps(consolidation_status_command(args.root, args.evidence, corpus=args.corpus, min_new=args.min_new),
                         ensure_ascii=False, indent=2))
        return 0

    if args.command == "observe":
        record = observe_command(args.evidence, args.source, json.loads(args.payload_json), args.outcome)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0

    if args.command == "remember":
        record = remember_command(args.evidence, json.loads(args.payload_json), args.outcome)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0

    if args.command == "consolidate-corpus":
        out = consolidate_corpus_command(args.root, args.evidence, write=args.write)
        if args.format == "json":
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(f"proposals: {len(out['proposals'])}")
            for proposal in out["proposals"]:
                print(f"  - {proposal['title']}")
            for gate in out["gates"]:
                print(f"  gate {gate['name']}: {'PASS' if gate['passed'] else 'FAIL'} {gate['detail']}")
            if out["written"]:
                print("written: " + ", ".join(out["written"]))
            if out["removed"]:
                print("removed: " + ", ".join(out["removed"]))
            if not out["written"] and not out["removed"]:
                print("no changes" if out["gates_ok"] else "blocked: gate failed")
        return 0 if out["gates_ok"] else 1

    if args.command == "consolidate":
        out = consolidate_command(args.memory, args.evidence, write=args.write)
        if args.format == "json":
            print(json.dumps(out, ensure_ascii=False, indent=2))
        else:
            print(f"proposals: {len(out['proposals'])}")
            for proposal in out["proposals"]:
                print(f"  - {proposal['title']}")
            print(out["diff"] or "(no change)")
            for gate in out["gates"]:
                print(f"  gate {gate['name']}: {'PASS' if gate['passed'] else 'FAIL'} {gate['detail']}")
            print("written" if out["written"] else ("dry-run (use --write)" if out["gates_ok"] else "blocked: gate failed"))
        return 0 if out["gates_ok"] else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
