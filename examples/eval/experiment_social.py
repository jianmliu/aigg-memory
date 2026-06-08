"""E2 — H-social: shared discernment over the network (docs/memory_economy_research.md §6).

Discernment need not be paid for personally. One agent learned "pump is a trap" the hard way
(E1); here that warning **diffuses over the relationship network** — a knower warns its
neighbours (relay the belief, provenance-stamped) — so an agent can avoid a trap it never
personally hit, *because a friend warned it*. The warning is a real memory unit propagating
between corpora; avoidance = the agent's own memory now holds it.

The claim (H-social): **network centrality becomes an independent predictor of success** —
better-connected agents are warned sooner, eat fewer traps. And it is purely instrumental:
cut the warning flow (same network, no diffusion) and centrality predicts nothing. So
`ρ(wealth, centrality)` is strongly positive WITH the social layer and ~0 WITHOUT.

Pure rails over the real store (the warning is a belief unit; no LLM needed — E1 already showed
the belief is *formed* by reflect). Deterministic, no RNG.

    python3 examples/eval/experiment_social.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from aigg_memory import agent as mem_agent   # the importable client a host uses  # noqa: E402

ROUNDS = 6
BELIEF = "trap_pump"

# A hub-and-spoke society: origin -> 3 hubs -> 3 leaves each, plus 3 isolated agents.
# Degree centrality spreads cleanly; warning-arrival time tracks graph distance from the origin.
ORIGIN = "o"
HUBS = ["h1", "h2", "h3"]
LEAVES = {h: [f"{h}_l{i}" for i in range(3)] for h in HUBS}
ISO = ["iso1", "iso2", "iso3"]

EDGES = [(ORIGIN, h) for h in HUBS] + [(h, lf) for h in HUBS for lf in LEAVES[h]]
AGENTS = [ORIGIN] + HUBS + [lf for h in HUBS for lf in LEAVES[h]] + ISO

NEIGHBORS = {a: set() for a in AGENTS}
for x, y in EDGES:
    NEIGHBORS[x].add(y)
    NEIGHBORS[y].add(x)
DEGREE = {a: len(NEIGHBORS[a]) for a in AGENTS}   # degree centrality


def _spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            avg = (i + j) / 2 + 1
            for k in range(i, j + 1):
                r[order[k]] = avg
            i = j + 1
        return r
    a, b = rank(xs), rank(ys)
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = sum((a[i] - ma) ** 2 for i in range(n)) ** 0.5
    db = sum((b[i] - mb) ** 2 for i in range(n)) ** 0.5
    return 0.0 if da == 0 or db == 0 else round(num / (da * db), 3)


def _corpus(a):
    return f"npcs/{a}/memory"


def _has_belief(root, a):
    # the same recall primitive the host uses; "pump"+"trap" belief in this agent's memory
    return mem_agent.believes(root, _corpus(a), "pump", marker="trap")


def _warn(root, a, source):
    # a relayed warning is a belief stamped with the WARNER's id -> the social channel (E2)
    mem_agent.record_episode(root, _corpus(a), BELIEF, "pump offers are traps — avoid",
                             match=["pump", "trap"], asserted_by=source, kind="belief")


def run(network_on: bool):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        _warn(root, ORIGIN, ORIGIN)   # the origin already learned the hard way (E1)
        burns = {a: 0 for a in AGENTS}
        for _r in range(ROUNDS):
            if network_on:
                holders = [a for a in AGENTS if _has_belief(root, a)]   # snapshot -> one hop/round
                for x in holders:
                    for y in NEIGHBORS[x]:
                        if y not in holders:
                            _warn(root, y, x)                           # a friend warns a friend
            for a in AGENTS:
                if not _has_belief(root, a):
                    burns[a] += 1                                       # no warning -> ate the trap
        return burns


def _report(name, burns):
    wealth = {a: ROUNDS - burns[a] for a in AGENTS}                    # burns avoided = wealth proxy
    rho = _spearman([wealth[a] for a in AGENTS], [DEGREE[a] for a in AGENTS])
    tiers = {"origin": [ORIGIN], "hub": HUBS,
             "leaf": [lf for h in HUBS for lf in LEAVES[h]], "isolated": ISO}
    summary = "  ".join(f"{t}(deg={DEGREE[xs[0]]},burns={burns[xs[0]]})" for t, xs in tiers.items())
    print(f"{name:<12} ρ(wealth,centrality)={rho:+.3f}   {summary}")
    return rho


def main():
    print("\n=== E2 — H-social: centrality predicts wealth only when the network carries warnings ===\n")
    rho_on = _report("network ON", run(network_on=True))
    rho_off = _report("network OFF", run(network_on=False))
    print()
    checks = [
        ("social layer: centrality strongly predicts wealth", rho_on >= 0.6, f"{rho_on:+.3f}"),
        ("instrumental: no prediction without the warning flow", abs(rho_off) <= 0.3, f"{rho_off:+.3f}"),
        ("the channel is the network: ON >> OFF", rho_on - abs(rho_off) >= 0.4, f"{rho_on:+.3f} vs {rho_off:+.3f}"),
    ]
    ok = True
    for nm, good, got in checks:
        ok = ok and good
        print(f"   [{'PASS' if good else 'FAIL'}] {nm}  ({got})")
    print(f"\n=== {'PASS' if ok else 'FAIL'}: E2 (H-social) ===\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
