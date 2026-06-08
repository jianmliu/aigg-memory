"""Generic, experiment-blind runner for aigg-memory behavioral evals — the MVP of
docs/experiment_harness.md.

It speaks ONLY the public surface: it starts a real `aigg-memory serve` (HTTP) and drives
the cognition-under-test (plan / reconcile / reflect) over HTTP; the LLM steps point at a
scripted **stub model** (a tiny OpenAI-compatible endpoint) so a run is fully deterministic
and needs no network or real model. Store *setup* writes unit files (the store's source of
truth — fixtures), and *measurement* (probes) reads those files back. No kernel code; no new
dependency beyond PyYAML (already required).

A manifest is data; the Runner is shared. Adding an experiment adds a manifest (+ maybe one
probe/verb in probes.py / verbs.py), never touches this file.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


# --- the scripted stub model (deterministic, no real LLM) -----------------

class StubModel:
    """A minimal OpenAI-compatible /chat/completions that replies from manifest rules. Each
    rule is {when:{system_contains?, user_contains?}, reply:"<string>"}; the first match wins.
    No match -> "[]" (which every parse_* tolerates as 'nothing'), so the kernel never acts on
    an unscripted call. This is the 'no dialogue LLM' headless model: only scripted cognition."""

    def __init__(self, rules):
        self.rules = rules or []
        self.port = _free_port()
        self._httpd = None
        self._thread = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    @staticmethod
    def _contains(haystack: str, needle) -> bool:
        """A rule matches when every needle (str, or all of a list) is a substring."""
        if needle is None:
            return True
        needles = needle if isinstance(needle, list) else [needle]
        return all(n in haystack for n in needles)

    def _reply_for(self, system: str, user: str) -> str:
        for rule in self.rules:
            when = rule.get("when", {})
            if self._contains(system, when.get("system_contains")) and \
               self._contains(user, when.get("user_contains")):
                return rule.get("reply", "[]")
        return "[]"

    def start(self):
        rules_owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # quiet
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length) or b"{}")
                msgs = {m.get("role"): m.get("content", "") for m in body.get("messages", [])}
                reply = rules_owner._reply_for(msgs.get("system", ""), msgs.get("user", ""))
                out = json.dumps({"choices": [{"message": {"content": reply}}]}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(out)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", self.port), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()


# --- a real `aigg-memory serve` subprocess --------------------------------

class ServeProcess:
    def __init__(self, root: Path):
        self.root = root
        self.port = _free_port()
        self._proc = None

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self):
        env = dict(os.environ)
        env["PYTHONPATH"] = str(SRC)
        env.pop("AIGG_MEMORY_BACKEND", None)  # never let an ambient backend leak in
        self._proc = subprocess.Popen(
            [sys.executable, "-m", "aigg_memory.cli", "serve",
             "--root", str(self.root), "--port", str(self.port)],
            cwd=str(REPO_ROOT), env=env,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 20
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"{self.base}/healthz", timeout=1) as r:
                    if r.status == 200:
                        return self
            except Exception:
                time.sleep(0.1)
        self.stop()
        raise RuntimeError("serve did not become healthy in time")

    def stop(self):
        if self._proc:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()


# --- the per-run context handed to verbs and probes -----------------------

class Ctx:
    """The per-run context handed to verbs and probes. Multi-corpus aware: with no `agent`,
    operations target the default corpus (single-agent, e.g. the memory-correctness run); with
    an `agent`, they target `npcs/<agent>/memory` (the mud sandbox — one corpus per NPC)."""

    def __init__(self, root: Path, serve: ServeProcess, model_url: str, now: str,
                 default_corpus: str = "memory"):
        self.root = root
        self.serve = serve
        self.model_url = model_url
        self.now = now
        self.default_corpus = default_corpus

    def corpus_of(self, agent=None) -> str:
        return f"npcs/{agent}/memory" if agent else self.default_corpus

    def http(self, path: str, body: dict) -> dict:
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.serve.base + path, data=data,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    @staticmethod
    def _parse(text: str):
        lines = text.splitlines()
        if lines and lines[0].strip() == "---":
            for i in range(1, len(lines)):
                if lines[i].strip() == "---":
                    fm = yaml.safe_load("\n".join(lines[1:i])) or {}
                    return fm if isinstance(fm, dict) else {}
        return {}

    def write_unit(self, corpus: str, slug: str, frontmatter: dict, body: str = "") -> None:
        path = self.root / corpus / slug / "SKILL.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        fm = yaml.safe_dump(frontmatter, sort_keys=False, allow_unicode=True).rstrip("\n")
        path.write_text(f"---\n{fm}\n---\n\n{(body or '').rstrip(chr(10))}\n", encoding="utf-8")

    def read_unit(self, corpus: str, slug: str):
        path = self.root / corpus / slug / "SKILL.md"
        return self._parse(path.read_text(encoding="utf-8")) if path.exists() else None

    def read_units(self, corpus: str) -> dict:
        """All units in a corpus as {slug: frontmatter} — the read-only view probes measure."""
        out = {}
        for skill in sorted((self.root / corpus).glob("*/SKILL.md")):
            out[skill.parent.name] = self._parse(skill.read_text(encoding="utf-8"))
        return out

    def agents(self) -> list:
        """Every NPC in the sandbox (a dir with npcs/<id>/memory/)."""
        base = self.root / "npcs"
        if not base.exists():
            return []
        return sorted(d.name for d in base.iterdir() if (d / "memory").is_dir())


# --- the runner -----------------------------------------------------------

def _run_once(manifest: dict, tmp_root: Path, skip_verbs=(), skip_steps=()):
    """Execute one condition (full run, or an ablation that skips some verbs / specific steps)
    in a fresh root, then sample every probe. Returns {probe_id: value}."""
    from verbs import VERBS
    from probes import PROBES

    skip = set(skip_verbs)
    skip_ids = set(skip_steps)
    corpus = manifest.get("world", {}).get("corpus", "memory")
    now = manifest.get("world", {}).get("now", "2026-06-08")
    stub = StubModel(manifest.get("model_script")).start()
    serve = ServeProcess(tmp_root).start()
    ctx = Ctx(tmp_root, serve, stub.url, now, default_corpus=corpus)
    try:
        for step in [*manifest.get("seed", []), *manifest.get("steps", [])]:
            verb = step["verb"]
            if verb in skip or step.get("id") in skip_ids:
                continue
            VERBS[verb](ctx, step.get("args", {}))
        values = {}
        for p in manifest.get("probes", []):
            values[p["id"]] = PROBES[p["probe"]](ctx, p.get("args", {}))
        return values
    finally:
        serve.stop()
        stub.stop()


def run_experiment(manifest: dict, workdir: Path) -> bool:
    """Run the full condition + every ablation, evaluate pass predicates, print a report.
    Returns True iff the full run passes and every ablation flips its declared probes."""
    probes_by_id = {p["id"]: p for p in manifest.get("probes", [])}

    full = _run_once(manifest, workdir / "full")
    ok = True
    print(f"\n=== {manifest['id']} — {manifest.get('name','')} ===")
    print("\n-- full run --")
    for pid, val in full.items():
        expect = probes_by_id[pid].get("expect")
        match = (val == expect)
        ok = ok and match
        print(f"   [{'PASS' if match else 'FAIL'}] {pid}: got {val!r}  expect {expect!r}")

    for ab in manifest.get("ablations", []):
        vals = _run_once(manifest, workdir / ab["id"],
                         skip_verbs=ab.get("skip_verbs", []), skip_steps=ab.get("skip_steps", []))
        skipped = ab.get("skip_verbs", []) + ab.get("skip_steps", [])
        print(f"\n-- ablation: {ab['id']} (skip {skipped}) --")
        flips = ab.get("expect_flip", [])
        for pid in flips:
            flipped = (vals.get(pid) != full.get(pid))
            ok = ok and flipped
            print(f"   [{'PASS' if flipped else 'FAIL'}] {pid} flipped: full {full.get(pid)!r} -> ablation {vals.get(pid)!r}")

    print(f"\n=== {'PASS' if ok else 'FAIL'}: {manifest['id']} ===\n")
    return ok
