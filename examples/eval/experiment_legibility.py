"""E4 — H-legibility: allocate capital by a memory track record, not by (lucky) wealth
(docs/memory_economy_research.md §6). Closes the research program.

In Talent-vs-Luck, current wealth = skill + LUCK (multiplicative shocks compound, so the richest
are often the luckiest, not the most skilled). A patron who allocates "meritocratically" by
current wealth therefore rewards luck — entrenching it. But a memory `track_record` is a
luck-FILTERED signal of skill: it counts the traps an agent learned to recognize itself (E1) —
something skill earns and luck cannot. So a patron allocating by track record allocates close to
true skill, beating meritocracy and approaching the talent oracle.

We sweep the ELC patron policies (meritocratic / egalitarian / talent / random) + the new
`track_record` policy, and read **realized-talent** = ρ(final wealth, true skill) and **Gini**.
Deterministic; `track_record` here stands in for agent.track_record reading the versioned store.

    python3 examples/eval/experiment_legibility.py
"""
import random

N, ROUNDS, SEED = 60, 30, 42
ENDOWMENT, SKILL_EARN, BUDGET = 1.0, 0.10, 6.0
LUCK = 0.18            # multiplicative luck amplitude (compounds -> wealth diverges from skill)
TRACK_NOISE = 0.05     # track_record is a near-clean skill signal (luck-free)

_s = random.Random(SEED)
SKILL = [round(0.2 + 0.8 * (i + 0.5) / N, 4) for i in range(N)]   # spread 0.2..1.0
_s.shuffle(SKILL)                                                  # skill ⟂ agent index
TRACK = [max(0.0, sk + _s.uniform(-TRACK_NOISE, TRACK_NOISE)) for sk in SKILL]  # skill, luck-free


def _spearman(xs, ys):
    def rank(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2 + 1
            i = j + 1
        return r
    a, b = rank(xs), rank(ys)
    n = len(a)
    ma, mb = sum(a) / n, sum(b) / n
    num = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    da = sum((a[i] - ma) ** 2 for i in range(n)) ** 0.5
    db = sum((b[i] - mb) ** 2 for i in range(n)) ** 0.5
    return 0.0 if da == 0 or db == 0 else round(num / (da * db), 3)


def _gini(v):
    v = sorted(max(0.0, x) for x in v)
    n, s = len(v), sum(v)
    if s == 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(v))
    return round((2 * cum) / (n * s) - (n + 1) / n, 3)


def _weights(policy, wealth, patron_rng):
    if policy == "talent":        return list(SKILL)                       # oracle upper bound
    if policy == "track_record":  return list(TRACK)                       # memory: luck-filtered skill
    if policy == "meritocratic":  return [max(0.0, w) for w in wealth]     # reward winners = reward luck
    if policy == "egalitarian":   return [1.0] * N
    return [patron_rng.random() for _ in range(N)]                          # random


def run(policy):
    # same seeded luck stream for every policy -> counterfactual-clean comparison
    luck_rng = random.Random(SEED * 1000 + 7)
    patron_rng = random.Random(SEED * 13 + 1)
    wealth = [ENDOWMENT] * N
    for _r in range(ROUNDS):
        for i in range(N):
            wealth[i] += SKILL[i] * SKILL_EARN                              # skill earns (effort)
            wealth[i] *= 1.0 + luck_rng.uniform(-LUCK, LUCK)                # luck compounds
        w = _weights(policy, wealth, patron_rng)
        tot = sum(w) or 1.0
        for i in range(N):
            wealth[i] += BUDGET * w[i] / tot                                # patron allocates
    return {"realized_talent": _spearman(wealth, SKILL), "gini": _gini(wealth)}


def main():
    print("\n=== E4 — H-legibility: capital by memory track record beats capital by (lucky) wealth ===\n")
    print(f"   {'patron policy':<16}{'realized-talent ρ(wealth,skill)':>32}{'Gini':>8}")
    rows = {}
    for p in ["talent", "track_record", "meritocratic", "egalitarian", "random"]:
        rows[p] = run(p)
        tag = {"talent": "  (oracle upper bound)", "track_record": "  ← memory", "meritocratic": "  (rewards luck)"}.get(p, "")
        print(f"   {p:<16}{rows[p]['realized_talent']:>+32.3f}{rows[p]['gini']:>8}{tag}")
    print()
    tr, me, ta = rows["track_record"], rows["meritocratic"], rows["talent"]
    checks = [
        ("track_record beats meritocratic on realized-talent", tr["realized_talent"] > me["realized_talent"] + 0.1, f"{tr['realized_talent']:+.3f} vs {me['realized_talent']:+.3f}"),
        ("track_record approaches the talent oracle", tr["realized_talent"] >= 0.85 * ta["realized_talent"], f"{tr['realized_talent']:+.3f} vs {ta['realized_talent']:+.3f}"),
        ("meritocratic entrenches luck -> higher Gini than track_record", me["gini"] > tr["gini"], f"Gini {me['gini']} vs {tr['gini']}"),
        ("meritocracy is fooled: realized-talent well below the oracle", me["realized_talent"] < 0.8 * ta["realized_talent"], f"{me['realized_talent']:+.3f} < {ta['realized_talent']:+.3f}"),
    ]
    ok = True
    for name, good, got in checks:
        ok = ok and good
        print(f"   [{'PASS' if good else 'FAIL'}] {name}  ({got})")
    print("\n   → meritocracy can't tell 'won' from 'got lucky'; the memory track record can — so it"
          " allocates by skill, not luck. Memory makes skill bankable.")
    print(f"\n=== {'PASS' if ok else 'FAIL'}: E4 (H-legibility) ===\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
