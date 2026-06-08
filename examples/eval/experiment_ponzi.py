"""E8 — the Ponzi fund vs memory (docs/memory_economy_research.md §7/§8). E6 re-anchored onto a
fund with a coverage ratio.

A Ponzi fund pays "returns" from NEW deposits, not from NAV. Its defining number is the coverage
ratio = NAV / liabilities: it is insolvent from the start (coverage < 1, falling), hidden only by
fresh money. It survives solely while inflows ≥ outflows, so it must keep recruiting new marks.

A memory-equipped investor audits the fund (NAV vs price; the provenance of past payouts — from
NAV growth or from new deposits; the manager's track record) and REFUSES to deposit. So the pool
of recruitable marks is (1 − memory) of the population: as memory penetration rises, the Ponzi
runs out of fresh money sooner -> its LIFESPAN collapses, and the fraudster's haul + the victim
count fall with it. A Ponzi needs darkness; memory is light.

We model the cabal only to MEASURE the control (the build target is the immune system, not the
fraud). Deterministic; pure fund-accounting model of the diffusion/immunity dynamics.

    python3 examples/eval/experiment_ponzi.py
"""
N, K, SEED = 1000, 80, 42                 # potential investors; marks recruited per round
UNIT, RETURN_RATE, SKIM = 1.0, 0.06, 0.2  # deposit; promised return/round; operator's cut of inflows
MAXR = 60
SWEEP = [0.0, 0.2, 0.4, 0.6, 0.8]


def run(memory: float):
    """A fraction `memory` audit and refuse; the Ponzi recruits only from the susceptible pool."""
    pool = int(round((1 - memory) * N))
    cash = total_dep = total_paid = haul = 0.0
    investors = 0
    cov0 = None
    r = 0
    while r < MAXR:
        recruits = min(K, pool)
        new_money = recruits * UNIT
        pool -= recruits
        cash += new_money * (1 - SKIM)        # operator skims the inflow (the fraud's take)
        haul += new_money * SKIM
        total_dep += new_money
        investors += recruits
        payout_due = RETURN_RATE * total_dep  # promised return on all principal, paid from cash
        if cov0 is None and total_dep:
            cov0 = cash / total_dep            # coverage right after launch (already < 1)
        if cash < payout_due:                  # can't meet obligations -> the run, collapse
            break
        cash -= payout_due
        total_paid += payout_due
        r += 1
    coverage = round(cash / total_dep, 3) if total_dep else 0.0
    return {"lifespan": r, "investors": investors, "haul": round(haul, 1),
            "cov0": round(cov0 or 0, 3), "cov_end": coverage}


def main():
    print("\n=== E8 — the Ponzi fund vs memory: coverage hides insolvency, memory starves it ===\n")
    print(f"   {'memory':>7}  {'lifespan':>9}  {'investors(marks)':>16}  {'fraud haul':>11}  {'coverage@start→collapse':>24}")
    rows = {}
    for m in SWEEP:
        r = run(m)
        rows[m] = r
        print(f"   {int(m*100):>6}%  {r['lifespan']:>9}  {r['investors']:>16}  {r['haul']:>11}  "
              f"{r['cov0']:>11} → {r['cov_end']:<10}")
    base, immune = rows[0.0], rows[0.8]
    mono_haul = all(rows[SWEEP[i]]["haul"] >= rows[SWEEP[i+1]]["haul"] for i in range(len(SWEEP)-1))
    mono_life = all(rows[SWEEP[i]]["lifespan"] >= rows[SWEEP[i+1]]["lifespan"] for i in range(len(SWEEP)-1))
    print()
    checks = [
        ("insolvent from launch: coverage < 1 (the hidden gap)", base["cov0"] < 1.0, f"cov0={base['cov0']}"),
        ("coverage collapses by the run (NAV never backed the shares)", immune["cov_end"] < 0.1, f"→ {immune['cov_end']}"),
        ("the fraud's REACH ~ (1 − memory): haul falls ~linearly", base["haul"] >= 4 * max(0.1, immune["haul"]), f"haul {base['haul']} → {immune['haul']}"),
        ("memory caps the victim count to the unaudited minority", base["investors"] >= 4 * max(1, immune["investors"]), f"marks {base['investors']} → {immune['investors']}"),
        ("memory also shortens its life (monotone)", mono_life and mono_haul, "yes" if (mono_life and mono_haul) else "no"),
    ]
    ok = True
    for name, good, got in checks:
        ok = ok and good
        print(f"   [{'PASS' if good else 'FAIL'}] {name}  ({got})")
    print(f"\n   → a Ponzi needs darkness. Audit the source of returns and its reach falls with memory: "
          f"haul {base['haul']} → {immune['haul']}, victims {base['investors']} → {immune['investors']} "
          "— it reaches only the minority who don't check.")
    print(f"\n=== {'PASS' if ok else 'FAIL'}: E8 (Ponzi fund vs memory) ===\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
