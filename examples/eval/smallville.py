"""Smallville at scale — a 25-agent emergence run generated from compact config (you can't
hand-write hundreds of steps; you generate them). Deterministic: a seeded RNG fixes the daily
place schedule, so the whole run replays identically.

Each tick, every agent goes to a place (seeded); within a place, agents pair up and (a) `meet`
— forming the relationship network — and (b) `converse` about a rumor in both directions. The
conditional `relay` rail means information moves only from someone who actually knows it, so a
single seeded rumor diffuses across the town through co-located conversation over the days, and
the network densifies. Pure rails + store-reading probes (no LLM, no HTTP) — so it scales and
stays deterministic. The ablation matrix isolates each mechanism.

    python3 examples/eval/run.py examples/eval/smallville.py

Reference bands (Generative Agents, arXiv:2304.03442, ~approx over 25 agents / 2 days):
  information diffusion: 1/25 (4%) -> ~8-12/25 (32-48%)   (partial — not everyone hears)
  network density:       ~0.167 -> ~0.74
"""
import random

N = 25
TICKS = 12
SEED = 42
GOSSIP_PROB = 0.6    # chance a co-located pair gossips the rumor (while it is still fresh)
GOSSIP_TICKS = 6     # the rumor is "news" only this long; after that people stop spreading it
                     # (it goes stale) but keep meeting — so diffusion stays PARTIAL (a stable
                     # fraction hear within the news window) while the network keeps densifying.
PLACES = ["cafe", "park", "store", "plaza"]
RUMOR = {"slug": "rumor_party", "match": ["party", "rumor", "cafe"],
         "description": "There's a Valentine party at the cafe on Feb 14"}


def build():
    rng = random.Random(SEED)
    agents = [f"a{i:02d}" for i in range(N)]
    origin = agents[0]

    seed = [{"verb": "fact", "args": {"agent": origin, "slug": RUMOR["slug"],
                                      "description": RUMOR["description"], "match": RUMOR["match"]}}]

    steps = []
    for _t in range(TICKS):
        fresh = _t < GOSSIP_TICKS   # the rumor still spreads only while it is fresh news
        where = {a: rng.choice(PLACES) for a in agents}
        for a in agents:
            steps.append({"verb": "move", "args": {"agent": a, "to": where[a]}})
        by_place = {}
        for a in agents:
            by_place.setdefault(where[a], []).append(a)
        for members in by_place.values():
            rng.shuffle(members)
            for k in range(0, len(members) - 1, 2):   # pair up co-located agents (<=1 talk/tick each)
                a, b = members[k], members[k + 1]
                steps.append({"verb": "meet", "args": {"a": a, "b": b}})   # always acquaint
                if fresh and rng.random() < GOSSIP_PROB:                   # gossip only while fresh
                    for x, y in ((a, b), (b, a)):
                        steps.append({"verb": "converse", "args": {
                            "a": x, "b": y, "slug": RUMOR["slug"], "source": RUMOR["slug"],
                            "description": RUMOR["description"], "match": RUMOR["match"]}})

    probes = [
        {"id": "knew",      "probe": "knows_count",         "args": {"matcher": "party"}, "min": 8, "max": 20},
        {"id": "traceable", "probe": "diffusion_traceable", "args": {"matcher": "party", "root": origin}, "expect": True},
        {"id": "density",   "probe": "relationship_density","args": {}, "min": 0.3},
    ]
    ablations = [
        {"id": "no_conversation", "skip_verbs": ["converse"], "expect_flip": ["knew"]},
        {"id": "no_encounters",   "skip_verbs": ["meet"],     "expect_flip": ["density"]},
    ]
    return {
        "id": "smallville_25",
        "name": f"Smallville at scale — {N} agents, {TICKS} ticks, generated from seed {SEED}",
        "claim": "A single seeded rumor diffuses across 25 agents through co-located conversation "
                 "(partial — not everyone hears), and the relationship network densifies, all from "
                 "rails; removing conversation collapses diffusion, removing encounters collapses density.",
        "world": {"adapter": "mud", "now": "2026-02-13T08:00"},
        "model_script": [],
        "seed": seed,
        "steps": steps,
        "probes": probes,
        "ablations": ablations,
    }
