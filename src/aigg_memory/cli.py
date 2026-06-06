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
    detect_contradictions,
    edit_unit,
    infer_dependencies,
    infer_temporal,
    memory_domain,
    reconcile,
    merge_into,
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


def consolidate_corpus_command(root: str, evidence_path: str, write: bool = False,
                               min_count: int = 2, allowed_principals=None) -> Dict[str, Any]:
    result = consolidate_corpus(root, _load_records(evidence_path), write=write, min_promote_count=min_count,
                                allowed_principals=allowed_principals)
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
    remember.add_argument("--asserted-by", default=None, dest="asserted_by",
                          help="who asserted this (the speaker's principal / EOA) — provenance + authority")

    corpus = sub.add_parser("consolidate-corpus", help="consolidate evidence into memory/<slug>/SKILL.md units")
    corpus.add_argument("--root", default=".", help="project root containing the memory/ directory")
    corpus.add_argument("--evidence", required=True)
    corpus.add_argument("--write", action="store_true", help="write changed units when all gates pass")
    corpus.add_argument("--format", choices=["text", "json"], default="text")
    corpus.add_argument("--min-count", type=int, default=2, dest="min_count",
                        help="repetition gate: how many observations before a fact is promoted (explicit remember: 1)")
    corpus.add_argument("--allowed-principal", action="append", dest="allowed_principals", default=None,
                        help="authority gate: only consolidate evidence asserted_by this principal/EOA (repeatable)")

    status = sub.add_parser("consolidation-status", help="readiness signal: how much evidence is pending consolidation")
    status.add_argument("--root", default=".")
    status.add_argument("--evidence", required=True)
    status.add_argument("--corpus", default="memory")
    status.add_argument("--min-new", type=int, default=1, dest="min_new")

    serve = sub.add_parser("serve", help="run the local JSON memory API + web UI")
    serve.add_argument("--root", default=".", help="project root holding the corpus + evidence")
    serve.add_argument("--port", type=int, default=8788)
    serve.add_argument("--host", default="127.0.0.1",
                       help="bind address; defaults to localhost. Pass 0.0.0.0 to expose on a trusted network")
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
    edit.add_argument("--valid-from", default=None, help="world-time the fact became true (ISO)")
    edit.add_argument("--valid-to", default=None, help="world-time the fact stopped being true (ISO)")
    pin = edit.add_mutually_exclusive_group()
    pin.add_argument("--pin", dest="pin", action="store_true", default=None,
                     help="add to the self-profile (always injected at session start)")
    pin.add_argument("--unpin", dest="pin", action="store_false", default=None, help="remove from the self-profile")
    lock = edit.add_mutually_exclusive_group()
    lock.add_argument("--lock", dest="lock", action="store_true", default=None,
                      help="owner-lock (e.g. a persona card): the automatic loop won't auto-update it")
    lock.add_argument("--unlock", dest="lock", action="store_false", default=None, help="remove the owner lock")

    ingest = sub.add_parser("ingest", help="extract memories from a chat transcript into the evidence store")
    ingest.add_argument("--transcript", required=True, help="path to a transcript text file")
    ingest.add_argument("--evidence", required=True)
    ingest.add_argument("--extractor", choices=["heuristic", "aigg"], default="heuristic")
    ingest.add_argument("--aigg-url", default=None, help="AIGG inference base URL (for --extractor aigg)")
    ingest.add_argument("--aigg-key", default=None)
    ingest.add_argument("--model", default="gpt-4o-mini")
    ingest.add_argument("--fallback-heuristic", action="store_true", dest="fallback_heuristic",
                        help="if the model extractor is unreachable, fall back to the heuristic (never lose a session)")
    ingest.add_argument("--asserted-by", default=None, dest="asserted_by",
                        help="stamp every extracted observation with who asserted it (the speaker's principal / EOA)")

    contra = sub.add_parser("detect-contradictions", help="use an AIGG model to find + resolve contradicting units")
    contra.add_argument("--root", default=".")
    contra.add_argument("--corpus", default="memory")
    contra.add_argument("--aigg-url", required=True)
    contra.add_argument("--aigg-key", default=None)
    contra.add_argument("--model", default="gpt-4o-mini")
    contra.add_argument("--threshold", type=float, default=0.6, help="similarity pre-filter for candidate pairs")
    contra.add_argument("--write", action="store_true", help="archive the loser of each contradiction")

    infer = sub.add_parser("infer-deps", help="use an AIGG model to build the dependency graph (directed edges)")
    infer.add_argument("--root", default=".")
    infer.add_argument("--corpus", default="memory")
    infer.add_argument("--aigg-url", required=True, help="AIGG inference base URL")
    infer.add_argument("--aigg-key", default=None)
    infer.add_argument("--model", default="gpt-4o-mini")
    infer.add_argument("--write", action="store_true", help="write the inferred deps into unit frontmatter")

    itemp = sub.add_parser("infer-temporal", help="use an AIGG model to assert temporal ordering edges (precedes)")
    itemp.add_argument("--root", default=".")
    itemp.add_argument("--corpus", default="memory")
    itemp.add_argument("--aigg-url", required=True, help="AIGG inference base URL")
    itemp.add_argument("--aigg-key", default=None)
    itemp.add_argument("--model", default="gpt-4o-mini")
    itemp.add_argument("--write", action="store_true", help="write the inferred precedes edges into frontmatter")

    timeline = sub.add_parser("timeline", help="units ordered by world-time (valid_from) — indexed temporal query")
    timeline.add_argument("--root", default=".")
    timeline.add_argument("--corpus", default="memory")
    timeline.add_argument("--as-of", default=None, help="only units whose valid interval contains this time")

    commitp = sub.add_parser("commit", help="commit the corpus state (git versioning; ensures repo + gitignore)")
    commitp.add_argument("--root", default=".")
    commitp.add_argument("--corpus", default="memory")
    commitp.add_argument("--message", required=True)

    profile = sub.add_parser("profile", help="the self-profile: pinned units always injected at session start")
    profile.add_argument("--root", default=".")
    profile.add_argument("--corpus", default="memory")

    recon = sub.add_parser("reconcile", help="reconcile new statements vs memory (correction / temporal change), via AIGG")
    recon.add_argument("--root", default=".")
    recon.add_argument("--corpus", default="memory")
    recon.add_argument("--aigg-url", required=True, help="AIGG inference base URL")
    recon.add_argument("--aigg-key", default=None)
    recon.add_argument("--model", default="gpt-4o-mini")
    recon.add_argument("--threshold", type=float, default=0.6)
    recon.add_argument("--now", default=None, help="ISO time to stamp temporal supersession (caller supplies the clock)")
    recon.add_argument("--write", action="store_true", help="apply the routing (archive/supersede/valid-time)")

    recall = sub.add_parser("recall", help="recall units matching a request (daemonless; mirrors /memory/select)")
    recall.add_argument("request", help="the query / user message to recall against")
    recall.add_argument("--root", default=".")
    recall.add_argument("--corpus", default="memory")
    recall.add_argument("--n-best", type=int, default=5)
    recall.add_argument("--retriever", choices=["keyword", "semantic", "hybrid"], default="hybrid")
    recall.add_argument("--kinds", default=None, help="comma-separated kinds to filter (procedural,semantic,episodic)")
    recall.add_argument("--include-deps", action="store_true", help="also pull a hit's prerequisite closure")

    compact = sub.add_parser("compact", help="merge near-duplicate units (defrag / remove redundancy)")
    compact.add_argument("--root", default=".")
    compact.add_argument("--corpus", default="memory")
    compact.add_argument("--threshold", type=float, default=0.85, help="similarity threshold (higher = more conservative)")
    compact.add_argument("--write", action="store_true", help="apply the merges (default: dry-run)")
    compact.add_argument("--commit", action="store_true", help="record the result as a git commit (nothing is destroyed)")

    merge = sub.add_parser("merge", help="unit-aware merge of another corpus into this one (field-level)")
    merge.add_argument("--root", default=".")
    merge.add_argument("--corpus", default="memory")
    merge.add_argument("--from", required=True, dest="from_root", help="the other corpus's root")
    merge.add_argument("--from-corpus", default="memory")
    merge.add_argument("--write", action="store_true", help="write the merged units (default: dry-run)")
    merge.add_argument("--commit", action="store_true", help="record the merge as a git commit")

    history = sub.add_parser("log", help="the memory history (versioned corpus)")
    history.add_argument("--root", default=".")
    history.add_argument("--corpus", default="memory")
    history.add_argument("-n", type=int, default=20)

    vdiff = sub.add_parser("diff", help="unit-level diff between two memory states")
    vdiff.add_argument("--root", default=".")
    vdiff.add_argument("--corpus", default="memory")
    vdiff.add_argument("--base", default="HEAD~1")
    vdiff.add_argument("--head", default="HEAD")

    vrestore = sub.add_parser("restore", help="bring a 'forgotten' state back from history (non-destructive)")
    vrestore.add_argument("ref")
    vrestore.add_argument("--root", default=".")
    vrestore.add_argument("--corpus", default="memory")

    args = parser.parse_args(argv)

    if args.command == "ingest":
        from aigg_memory.extract import AIGGExtractor, HeuristicExtractor, ingest_transcript
        if args.extractor == "aigg" and not args.aigg_url:
            print("--aigg-url is required for --extractor aigg", file=sys.stderr)
            return 2
        transcript = Path(args.transcript).read_text(encoding="utf-8")
        used = args.extractor
        try:
            extractor = (AIGGExtractor(args.aigg_url, api_key=args.aigg_key, model=args.model)
                         if args.extractor == "aigg" else HeuristicExtractor())
            records = ingest_transcript(transcript, extractor, args.evidence, asserted_by=args.asserted_by)
        except Exception as exc:
            if args.extractor == "aigg" and args.fallback_heuristic:
                used = "heuristic"
                records = ingest_transcript(transcript, HeuristicExtractor(), args.evidence, asserted_by=args.asserted_by)
            else:
                print(f"extraction failed: {type(exc).__name__}: {exc}", file=sys.stderr)
                return 1
        print(json.dumps({"extracted": len(records), "extractor": used, "records": records},
                         ensure_ascii=False, indent=2))
        return 0

    if args.command == "detect-contradictions":
        from aigg_memory.extract import AIGGContradictionDetector
        detector = AIGGContradictionDetector(args.aigg_url, api_key=args.aigg_key, model=args.model)
        out = detect_contradictions(args.root, args.corpus, detector, threshold=args.threshold, write=args.write)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.command == "infer-deps":
        from aigg_memory.extract import AIGGDependencyInferrer
        inferrer = AIGGDependencyInferrer(args.aigg_url, api_key=args.aigg_key, model=args.model)
        out = infer_dependencies(args.root, args.corpus, inferrer, write=args.write)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.command == "infer-temporal":
        from aigg_memory.extract import AIGGTemporalInferrer
        inferrer = AIGGTemporalInferrer(args.aigg_url, api_key=args.aigg_key, model=args.model)
        out = infer_temporal(args.root, args.corpus, inferrer, write=args.write)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.command == "timeline":
        from aigg_memory.index import CorpusIndex
        idx = CorpusIndex(args.root, args.corpus)
        rows = idx.as_of(args.as_of) if args.as_of else idx.timeline()
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if args.command == "commit":
        from aigg_memory import versioning as vcs
        h = vcs.commit(Path(args.root) / args.corpus, args.message)
        print(json.dumps({"commit": h}, ensure_ascii=False))
        return 0

    if args.command == "profile":
        from aigg_memory.index import CorpusIndex
        print(json.dumps({"profile": CorpusIndex(args.root, args.corpus).profile()},
                         ensure_ascii=False, indent=2))
        return 0

    if args.command == "reconcile":
        from aigg_memory.extract import AIGGReconciler
        judge = AIGGReconciler(args.aigg_url, api_key=args.aigg_key, model=args.model)
        out = reconcile(args.root, args.corpus, judge, threshold=args.threshold, write=args.write, now=args.now)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.command == "recall":
        from aigg_memory.index import select_and_count
        kinds = [k.strip() for k in args.kinds.split(",")] if args.kinds else None
        units, total = select_and_count(args.root, args.corpus, args.request, n_best=args.n_best,
                                        kinds=kinds, include_deps=args.include_deps, retriever=args.retriever)
        print(json.dumps({"units": units, "total_in_corpus": total}, ensure_ascii=False, indent=2))
        return 0

    if args.command == "merge":
        result = merge_into(args.root, args.corpus, args.from_root, args.from_corpus, write=args.write)
        out = {"auto_resolved": result.auto_resolved, "conflicts": result.conflicts}
        if args.write and args.commit:
            from aigg_memory import versioning as vcs
            out["commit"] = vcs.commit(Path(args.root) / args.corpus,
                                       f"merge: {len(result.auto_resolved)} unit(s), {len(result.conflicts)} conflict(s)")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if not result.conflicts else 1

    if args.command in ("log", "diff", "restore"):
        from aigg_memory import versioning as vcs
        corpus_dir = Path(args.root) / args.corpus
        if args.command == "log":
            print("\n".join(vcs.log(corpus_dir, n=args.n)) or "(no history)")
        elif args.command == "diff":
            print(json.dumps(vcs.diff(corpus_dir, base=args.base, head=args.head), ensure_ascii=False, indent=2))
        else:
            try:
                vcs.restore(corpus_dir, args.ref)
            except ValueError as exc:
                print(str(exc), file=sys.stderr)
                return 1
            print(f"restored corpus to {args.ref}")
        return 0

    if args.command == "compact":
        result = compact_corpus(args.root, corpus=args.corpus, threshold=args.threshold, write=args.write)
        out = {"merged": result.merged, "written": result.written, "removed": result.removed}
        if args.commit and (result.written or result.removed):
            from aigg_memory import versioning as vcs
            folded = sum(len(m["folded"]) for m in result.merged)
            out["commit"] = vcs.commit(Path(args.root) / args.corpus, f"compact: folded {folded} duplicate unit(s)")
        print(json.dumps(out, ensure_ascii=False, indent=2))
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
                          "depended_by": idx.depended_by(args.slug), "supersedes": idx.supersedes(args.slug),
                          "precedes": idx.precedes(args.slug), "preceded_by": idx.preceded_by(args.slug)},
                         ensure_ascii=False, indent=2))
        return 0

    if args.command == "edit":
        out = edit_unit(args.root, args.corpus, args.slug, body=args.body,
                        description=args.description, status=args.status,
                        valid_from=args.valid_from, valid_to=args.valid_to, pinned=args.pin, locked=args.lock)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out["updated"] else 1

    if args.command == "serve":
        from aigg_memory.server import run_server
        if args.host == "0.0.0.0" and not args.token:
            print("aigg-memory serve: WARNING binding 0.0.0.0 without --token — the API is "
                  "unauthenticated on all interfaces.", file=sys.stderr)
        print(f"aigg-memory serve — root={args.root} http://{args.host}:{args.port}", file=sys.stderr)
        try:
            run_server(args.root, port=args.port, token=args.token, host=args.host)
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
        payload = json.loads(args.payload_json)
        if args.asserted_by:
            payload["asserted_by"] = args.asserted_by
        record = remember_command(args.evidence, payload, args.outcome)
        print(json.dumps(record, ensure_ascii=False, indent=2))
        return 0

    if args.command == "consolidate-corpus":
        out = consolidate_corpus_command(args.root, args.evidence, write=args.write, min_count=args.min_count,
                                         allowed_principals=args.allowed_principals)
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
