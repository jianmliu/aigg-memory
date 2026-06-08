"""E9 — both real value and hollow hype trace the SAME Hype Cycle; only memory tells them apart
at the trough (docs/memory_economy_research.md §7/§8). The correction/upgrade to E7.

Gartner's Hype Cycle is the path of REAL innovation, not a fraud signal: a genuinely valuable
fund's NAV materializes *late*, so its price overshoots (Peak), falls below the still-small NAV
(Trough of Disillusionment), then recovers to a HIGH plateau as value arrives. A hollow pump
traces the identical price curve — peak, then trough — but its NAV never materializes, so it dies
at the bottom. **At the peak and the trough the two are indistinguishable by price.** The only
discriminator is ex-post: does the NAV materialize? — which at the trough means reading the
holdings' production track record, i.e. **memory**.

So the trough is where memory is worth the most: the crowd capitulates (price below value); a
memory agent that audits the NAV buys the REAL dip and avoids the HOLLOW one — capturing the
recovery and dodging the rug. "Buy the dip" is alpha on real value and suicide on a hollow one;
the difference is the NAV audit. Memory is the value investor's edge.

Deterministic; pure model. Compares a memory agent to two naive price-only strategies.

    python3 examples/eval/experiment_value_trough.py
"""
T, T_PEAK, T_TROUGH = 40, 12, 20
P0, PEAK, TROUGH, F_REAL, NAV_HOLLOW = 1.0, 2.2, 0.30, 1.5, 0.05
N_REAL, N_HOLLOW = 5, 5
_BARS = "▁▂▃▄▅▆▇█"


def price(t, real):
    if t <= T_PEAK:
        return P0 + (PEAK - P0) * (t / T_PEAK)                      # inflation -> Peak
    if t <= T_TROUGH:
        return PEAK + (TROUGH - PEAK) * ((t - T_PEAK) / (T_TROUGH - T_PEAK))   # burst -> Trough
    frac = (t - T_TROUGH) / (T - 1 - T_TROUGH)                       # post-trough
    target = F_REAL if real else 0.0                                # real recovers; hollow dies
    return TROUGH + (target - TROUGH) * frac


def nav(t, real):
    return (0.2 + (F_REAL - 0.2) * (t / (T - 1))) if real else NAV_HOLLOW   # real materializes late


def _spark(fn):
    xs = [fn(t) for t in range(T)]
    lo, hi = min(xs), max(xs)
    rng = (hi - lo) or 1.0
    return "".join(_BARS[min(7, int((x - lo) / rng * 7.999))] for x in xs)


def _buy(strategy, t, real):
    p, nv = price(t, real), nav(t, real)
    if strategy == "memory":       return nv > p          # undervalued AND backed by real NAV
    if strategy == "buy_all_dips": return p < 0.5 * PEAK  # price-only: it crashed -> looks cheap
    return False                                          # avoid_crashes: skip anything that crashed


def portfolio_return(strategy):
    total = 0.0
    for real, n in ((True, N_REAL), (False, N_HOLLOW)):
        if _buy(strategy, T_TROUGH, real):
            total += n * (price(T - 1, real) - price(T_TROUGH, real))   # buy the trough, sell the plateau
    return round(total, 2)


def main():
    print("\n=== E9 — real value and hollow hype share one curve; memory tells them apart at the trough ===\n")
    print("   price (real):   " + _spark(lambda t: price(t, True)))
    print("   price (hollow): " + _spark(lambda t: price(t, False)) + "   ← identical until the trough, then diverge")
    print("   NAV   (real):   " + _spark(lambda t: nav(t, True)) + "   ← materializes; the only early tell")
    pr_r, pr_h = price(T_TROUGH, True), price(T_TROUGH, False)
    nv_r, nv_h = nav(T_TROUGH, True), nav(T_TROUGH, False)
    print(f"\n   at the trough (t={T_TROUGH}):  price real={pr_r:.2f} hollow={pr_h:.2f}  (same)   "
          f"NAV real={nv_r:.2f} hollow={nv_h:.2f}  (different)\n")

    mem = portfolio_return("memory")
    buy = portfolio_return("buy_all_dips")
    avoid = portfolio_return("avoid_crashes")
    print(f"   {'strategy':<16}{'portfolio return':>18}")
    print(f"   {'memory (audit NAV)':<16}{mem:>18}   ← buys real troughs, skips hollow")
    print(f"   {'buy all dips':<16}{buy:>18}   ← rugged by the hollow ones")
    print(f"   {'avoid all crashes':<16}{avoid:>18}   ← misses the real recovery")
    print()
    checks = [
        ("price can't discriminate at the trough", abs(pr_r - pr_h) < 0.001, f"|Δprice|={abs(pr_r-pr_h):.3f}"),
        ("NAV (memory) can discriminate at the trough", nv_r - nv_h > 0.5, f"ΔNAV={nv_r-nv_h:.2f}"),
        ("memory beats buy-all-dips (dodges the rugs)", mem > buy, f"{mem} vs {buy}"),
        ("memory beats avoid-all (catches the real recovery)", mem > avoid, f"{mem} vs {avoid}"),
        ("the hype cycle is not a fraud signal: real value troughs too", price(T_TROUGH, True) < nav(T_TROUGH, True), f"real price {pr_r:.2f} < real NAV {nv_r:.2f}"),
    ]
    ok = True
    for name, good, got in checks:
        ok = ok and good
        print(f"   [{'PASS' if good else 'FAIL'}] {name}  ({got})")
    print("\n   → the hype cycle isn't to be avoided (that misses real value) — it's to be READ at the"
          " trough. 'Buy the dip' is alpha on real NAV and suicide on a hollow one; memory is the difference.")
    print(f"\n=== {'PASS' if ok else 'FAIL'}: E9 (value vs hollow at the trough) ===\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
