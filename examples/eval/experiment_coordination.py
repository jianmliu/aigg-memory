"""E3 (unified) — coordination is identical machinery; only the VALUE SOURCE separates a
productive venture from a pump cabal, and only MEMORY can read that difference
(docs/memory_economy_research.md §4/§6).

A challenge resolved: "isn't a coalition-only opportunity just a group pump?" In a purely
reflexive market — yes. The coordination machinery (a leader assembles a coalition that acts
together) is the SAME. The only thing that differs is where the payoff comes from:

  value_source = production : an external beneficiary PAYS for value the coalition produced and
                             is BETTER OFF  -> counterparty welfare POSITIVE  (a venture).
  value_source = reflexive  : the payoff is a transfer from recruited marks who BAG-HOLD
                             -> counterparty welfare NEGATIVE  (a pump cabal, cf. E6).

Two facts this experiment establishes:
  1. ρ(wealth, coordination) is POSITIVE in BOTH — coordinators win either way, so the
     wealth-correlation CANNOT tell a venture from a pump. The discriminator is the
     **counterparty welfare sign**, not the correlation.
  2. `track_record` (the provenance-stamped, versioned history of whether your past
     counterparties ended up better or worse) makes that sign LEGIBLE. With memory, members
     refuse leaders whose history harmed counterparties -> pump coalitions starve, productive
     ventures thrive. Memory sorts the economy toward value creation — and makes "coordination
     pays" true ONLY when coordination creates value.

Deterministic, seeded; pure model (the track_record signal stands in for agent.track_record
reading the versioned store).

    python3 examples/eval/experiment_coordination.py
"""
import random

L, SEED = 40, 42
PATRON_SURPLUS = 0.5    # production: beneficiary nets +0.5*size (value 1.5*size, pays size)

_rng = random.Random(SEED)
# coordination ability spreads 1..L; type is independent of it (seeded coin) so type ⟂ skill.
LEADERS = [{"id": i, "coord": i + 1, "type": "predatory" if _rng.random() < 0.5 else "productive"}
           for i in range(L)]


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


def run(memory: bool):
    """Each leader assembles a coalition and acts. With memory, members check the leader's
    track record (does its history harm counterparties?) and refuse predatory leaders."""
    wealth, coord, counterparty, pred_profit, marks = [], [], 0.0, 0.0, 0
    for ld in LEADERS:
        c = ld["coord"]
        # the join decision: with memory, members read track_record (= sign of past counterparty
        # welfare) and refuse a predatory leader -> its coalition can't assemble.
        assembles = (not memory) or ld["type"] == "productive"
        if not assembles:
            w, cp = 0.0, 0.0
        elif ld["type"] == "productive":
            w = float(c)                 # the venture's take
            cp = PATRON_SURPLUS * c      # the external beneficiary is BETTER off
        else:  # predatory: a pump — the leader dumps on c recruited marks
            w = float(c)                 # captured from the marks
            cp = -float(c)               # the marks (counterparty) are WORSE off
            pred_profit += c
            marks += c
        wealth.append(w)
        coord.append(c)
        counterparty += cp
    return {"rho": _spearman(wealth, coord), "counterparty": round(counterparty, 1),
            "pred_profit": round(pred_profit, 1), "marks": marks}


def main():
    off = run(memory=False)
    on = run(memory=True)
    print("\n=== E3 (unified) — coordination: venture vs pump is one knob (value source), "
          "legible only by memory ===\n")
    print(f"   {'condition':<16}{'ρ(wealth,coord)':>16}{'counterparty welfare':>22}{'pump profit':>13}{'marks rugged':>14}")
    print(f"   {'memory OFF':<16}{off['rho']:>+16.3f}{off['counterparty']:>22}{off['pred_profit']:>13}{off['marks']:>14}")
    print(f"   {'memory ON':<16}{on['rho']:>+16.3f}{on['counterparty']:>22}{on['pred_profit']:>13}{on['marks']:>14}")
    print()
    checks = [
        ("coordination pays regardless of kind (can't distinguish by wealth)", off["rho"] >= 0.99, f"ρ={off['rho']:+.3f}"),
        ("the discriminator is the counterparty sign: pumps make it NEGATIVE", off["counterparty"] < 0, f"{off['counterparty']}"),
        ("memory reads track_record -> pumps starve", on["pred_profit"] == 0 and on["marks"] == 0, f"profit={on['pred_profit']}, marks={on['marks']}"),
        ("memory flips total welfare positive (only ventures remain)", on["counterparty"] > 0, f"{off['counterparty']} -> {on['counterparty']}"),
        ("with memory, coordination pays ONLY if it creates value", on["rho"] < off["rho"], f"ρ {off['rho']:+.3f} -> {on['rho']:+.3f}"),
    ]
    ok = True
    for name, good, got in checks:
        ok = ok and good
        print(f"   [{'PASS' if good else 'FAIL'}] {name}  ({got})")
    print("\n   → same coordination machinery; venture (counterparty better) vs pump (counterparty"
          " worse) is one knob. Wealth-correlation can't tell them apart — memory can.")
    print(f"\n=== {'PASS' if ok else 'FAIL'}: E3 (unified coordination) ===\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
