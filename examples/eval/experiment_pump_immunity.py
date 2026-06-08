"""E6 — the pump cabal vs memory herd-immunity (docs/memory_economy_research.md §7/§8).

The dual of E2. The relationship network is a NEUTRAL channel: E2 used it to spread *warnings*
(defensive, positive-sum — a warning helps everyone). The SAME machinery builds a pump cabal: a
manipulator's "buy now, bring others" signal cascades through the network, and **earlier = more
profit** (you front-run the price you collectively create; the late marks you recruited bag-hold).

But a follower must be a MARK — naive, no memory. A memory-equipped agent (E5: it holds a "this
caller pumps" belief / checks the track record) REFUSES and does not transmit, so it blocks the
cascade. So the pump is a percolation on the susceptible (memoryless) sub-network: above a
**memory-penetration threshold** the susceptible cluster shatters and the pump cannot recruit
enough marks — it dies. A society that remembers can't be pumped, because there are no marks.

We model the cabal only to MEASURE that immunity (the build target is the immune system, not the
pathogen). Site percolation over a random peer network (redundant paths, so the pump can route
around some immune nodes -> a fair threshold, not the fragile single-path pyramid), seeded ->
deterministic.

    python3 examples/eval/experiment_pump_immunity.py
"""
import random

N, AVG_DEG, SEED = 600, 6, 42      # random peer network; site-percolation threshold m* ≈ 1 - 1/<k>
SWEEP = [0.0, 0.3, 0.5, 0.6, 0.7, 0.8, 0.9]

# build a seeded Erdos–Renyi graph (node 0 = the manipulator, seed of the pump)
_g = random.Random(SEED)
_p = AVG_DEG / (N - 1)
ADJ = {i: set() for i in range(N)}
for _i in range(N):
    for _j in range(_i + 1, N):
        if _g.random() < _p:
            ADJ[_i].add(_j)
            ADJ[_j].add(_i)
_rank_rng = random.Random(SEED + 1)
RANK = {i: _rank_rng.random() for i in range(1, N)}   # stable per-node key -> nested immune sets


def run(memory_penetration: float):
    """A fraction `m` of agents are memory-immune (refuse to follow + don't relay the pump); the
    pump percolates from the manipulator through the susceptible (memoryless) peers only. BFS
    distance = recruitment earliness."""
    immune = {i for i in range(1, N) if RANK[i] < memory_penetration}
    dist = {0: 0}
    frontier = [0]
    while frontier:
        nxt = []
        for u in frontier:
            for v in ADJ[u]:
                if v not in immune and v not in dist:
                    dist[v] = dist[u] + 1
                    nxt.append(v)
        frontier = nxt
    recruited = [v for v in dist if v != 0]
    cabal = [v for v in recruited if dist[v] <= 2]   # recruited earliest -> in on the dump (profit)
    marks = [v for v in recruited if dist[v] > 2]     # late -> bag-hold the crash (rugged)
    return {"recruited": len(recruited), "cabal": len(cabal), "marks": len(marks),
            "manip_profit": len(marks), "welfare_loss": round(0.4 * len(marks), 1)}


def main():
    mstar = 1 - 1 / AVG_DEG
    print(f"\n=== E6 — pump cabal vs memory herd-immunity "
          f"(N={N}, <k>={AVG_DEG}, percolation m*≈{mstar:.2f}) ===\n")
    print(f"   {'mem%':>5}  {'recruited':>9}  {'marks_rugged':>12}  {'manip_profit':>12}  {'welfare_loss':>12}")
    rows = {}
    for m in SWEEP:
        r = run(m)
        rows[m] = r
        print(f"   {m*100:>4.0f}%  {r['recruited']:>9}  {r['marks']:>12}  {r['manip_profit']:>12}  {r['welfare_loss']:>12}")

    naive = rows[SWEEP[0]]
    collapsed = next((m for m in SWEEP if rows[m]["recruited"] < 0.05 * N), None)
    monotone = all(rows[SWEEP[i]]["recruited"] >= rows[SWEEP[i + 1]]["recruited"] for i in range(len(SWEEP) - 1))
    max_drop = max(rows[SWEEP[i]]["recruited"] / max(1, rows[SWEEP[i + 1]]["recruited"])
                   for i in range(len(SWEEP) - 1))
    print()
    checks = [
        ("naive society: the pump recruits widely", naive["recruited"] > 0.8 * N, f"{naive['recruited']}/{N}"),
        ("herd immunity: enough memory kills the pump", collapsed is not None, f"collapses at {int(collapsed*100) if collapsed else '—'}% memory"),
        ("monotone: more memory -> less reach", monotone, "yes" if monotone else "no"),
        ("a sharp percolation threshold (>=5x drop somewhere)", max_drop >= 5, f"max step drop {max_drop:.1f}x"),
        ("earliness pays (naive): cabal profits, marks bag-hold", naive["cabal"] > 0 and naive["marks"] > 0, f"cabal={naive['cabal']}, marks={naive['marks']}"),
    ]
    ok = True
    for name, good, got in checks:
        ok = ok and good
        print(f"   [{'PASS' if good else 'FAIL'}] {name}  ({got})")
    last = rows[SWEEP[-1]]
    print(f"\n   → a society that remembers can't be pumped: manip profit "
          f"{naive['manip_profit']} -> {last['manip_profit']} as memory crosses the threshold.")
    print(f"\n=== {'PASS' if ok else 'FAIL'}: E6 (pump cabal vs herd immunity) ===\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
