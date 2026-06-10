"""End-to-end proof of the mud-demo 'minimal PR' loop — REAL HTTP serve, NESTED corpus
(`npcs/<id>/memory`), REAL local model (Ollama gemma4). The exact shape the MUD will run:

  remember(outcome=…) → reflect(gemma4) → remember(another outcome) → verify → discernment

Pass = the NPC formed a belief from its episodes, the belief accrued verified confidence from an
uncited episode, and discernment (provenance mode, θ-gated) reads it back over HTTP.

Usage: python3 examples/eval/npc_loop_e2e.py     (needs ollama serve + gemma4 pulled)
"""
import json
import sys
import tempfile
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harness import ServeProcess   # noqa: E402

CORPUS = "npcs/sage/memory"        # the nested per-NPC corpus shape mud-demo uses
EVIDENCE = "npcs/sage/evidence.jsonl"
OLLAMA = "http://localhost:11434/v1"
MODEL = "gemma4:latest"


def post(base: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(base + path, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=150) as r:
        return json.loads(r.read())


def remember(base, slug, desc, **payload):
    return post(base, "/memory/remember", {"evidence": EVIDENCE, "corpus": CORPUS,
                                           "payload": {"slug": slug, "kind": "episodic",
                                                       "description": desc, **payload}})


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        serve = ServeProcess(Path(tmp)).start()
        base = serve.base
        ok = True
        try:
            print(f"=== NPC cognition loop e2e — nested corpus {CORPUS}, real {MODEL}, real HTTP ===\n")

            # 1. the NPC gets burned twice (the host tags outcomes — the verification input)
            for i, where in enumerate(["at the bridge", "in the market"]):
                r = remember(base, f"burn_pump_{i}", f"engaged a pump {where} and lost gcc",
                             match=["pump", "trap"], outcome="loss")
                assert r["ok"], r
            print("1. two outcome-tagged burn episodes written over HTTP ✓")

            # 2. nightly Dream: reflect over the REAL local model -> a belief
            r = post(base, "/memory/reflect", {"corpus": CORPUS, "aigg_url": OLLAMA, "model": MODEL,
                                               "timeout": 120, "write": True, "threshold": 0.2})
            written = (r.get("data") or {}).get("written") or []
            print(f"2. reflect over {MODEL}: belief(s) written = {written} {'✓' if written else '✗'}")
            ok &= bool(written)

            # 3. a third, uncited burn — the belief's first real test
            remember(base, "burn_pump_2", "a third pump rugged the sage near the docks",
                     match=["pump"], outcome="loss")

            # 4. verify sweep: the belief accrues confidence from the uncited episode
            r = post(base, "/memory/verify", {"corpus": CORPUS, "write": True, "now": "2026-06-10T22:00"})
            verified = (r.get("data") or {}).get("verified") or {}
            top = max(verified.values(), key=lambda v: v.get("confidence", 0)) if verified else {}
            print(f"4. verify: {len(verified)} belief(s) scored; best = "
                  f"hits={top.get('hits')} misses={top.get('misses')} confidence={top.get('confidence', 0):.3f} "
                  f"{'✓' if top.get('hits', 0) >= 1 else '✗ (no uncited hit — model cited all burns)'}")
            ok &= bool(verified)

            # 5. the turn-loop decision: discernment by evidence, θ-gated
            r = post(base, "/memory/discernment", {"corpus": CORPUS, "topic": "pump",
                                                   "mode": "provenance", "min_confidence": 0.5})
            d = r.get("data") or {}
            print(f"5. discernment(pump, provenance, θ=0.5): q={d.get('q')} faculty={d.get('faculty')} "
                  f"confidence={d.get('confidence', 0):.3f} {'✓' if d.get('q') == 1.0 else '✗'}")
            ok &= d.get("q") == 1.0

            print(f"\n=== {'PASS' if ok else 'FAIL'}: the full cognition loop "
                  f"(remember→reflect→verify→discernment) over HTTP + nested corpus + {MODEL} ===")
            sys.exit(0 if ok else 1)
        finally:
            serve.stop()


if __name__ == "__main__":
    main()
