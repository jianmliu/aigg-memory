"""E7 — the Gartner Hype Cycle is the natural waveform of reflexive belief, and memory is its
damper (docs/memory_economy_research.md §7/§8).

A single asset has a fixed fundamental value F. An inflated expectation diffuses through the
population (E2); each memoryless agent who hears it buys the hype (belief = HYPE > F), so the
price — the mean belief — OVERSHOOTS F (Peak of Inflated Expectations). Then reality arrives:
those agents `reconcile` expectation against the realized fundamental, the overshoot reverts and
overcorrects (Trough of Disillusionment); `reflect` on the real experience converges belief back
to F (Slope of Enlightenment → Plateau of Productivity). The price trace is the Hype Cycle.

A memory-equipped agent has seen past cycles (a "hype peaks revert" meta-belief), so when the
hype reaches it, it does NOT buy the top — it holds F. As memory penetration rises, fewer agents
overshoot: the hype AMPLITUDE shrinks ~ (1 − memory). A society that all remembers prices the
asset correctly with no bubble — the efficient-market limit.

Deterministic; pure model of the diffusion → reconcile → reflect dynamics we built.

    python3 examples/eval/experiment_hype_cycle.py
"""
import math
import random

N, T, T_REAL, SEED = 500, 40, 20, 42
F, HYPE, TROUGH, DECAY = 1.0, 2.0, 0.4, 0.6   # fundamental / overshoot / overcorrection / recovery
T0, KG = 11, 0.55                              # logistic adoption (hype diffuses, saturates ~T_REAL)
SWEEP = [0.0, 0.25, 0.5, 0.75, 1.0]
_BARS = "▁▂▃▄▅▆▇█"

_rng = random.Random(SEED)
RANK = [_rng.random() for _ in range(N)]        # memory ⟂ adoption order; nested immune sets


def _aware(t):
    return min(N, int(N / (1 + math.exp(-KG * (t - T0)))))   # cumulative adopters by tick t


def trace(memory: float):
    """Price (= mean belief) per tick. Memoryless adopters buy the hype then get disillusioned;
    memory agents (a fraction `memory`) see through it and hold the fundamental."""
    immune = {i for i in range(N) if RANK[i] < memory}
    prices = []
    for t in range(T):
        na = _aware(t)
        tot = 0.0
        for i in range(N):
            if i >= na:                       # not yet in the market
                b = F
            elif i in immune:                 # remembers past cycles -> never buys the top
                b = F
            elif t < T_REAL:                  # memoryless, hype phase -> rides the overshoot
                b = HYPE
            else:                             # memoryless, post-reality -> disillusion then recover
                b = F + (TROUGH - F) * (DECAY ** (t - T_REAL))
            tot += b
        prices.append(tot / N)
    return prices


def _spark(xs):
    lo, hi = min(xs), max(xs)
    rng = (hi - lo) or 1.0
    return "".join(_BARS[min(7, int((x - lo) / rng * 7.999))] for x in xs)


def main():
    base = trace(0.0)
    peak_t = max(range(T), key=lambda t: base[t])
    trough_t = min(range(peak_t, T), key=lambda t: base[t])
    print("\n=== E7 — the Hype Cycle as reflexive belief's waveform; memory is the damper ===\n")
    print(f"   fundamental F={F}.  price = mean belief.  reality hits at t={T_REAL}.\n")
    print(f"   memory  0%:  {_spark(base)}")
    print(f"                trigger→  peak(t={peak_t},{base[peak_t]:.2f})  "
          f"trough(t={trough_t},{base[trough_t]:.2f})  plateau({base[-1]:.2f})\n")

    print(f"   {'memory':>7}  {'peak':>6}  {'amplitude(peak-F)':>18}  {'trace':<42}")
    rows = {}
    for m in SWEEP:
        tr = trace(m)
        amp = round(max(tr) - F, 3)
        rows[m] = {"peak": round(max(tr), 3), "amp": amp, "trough": round(min(tr[peak_t:]), 3)}
        print(f"   {int(m*100):>6}%  {max(tr):>6.2f}  {amp:>18}  {_spark(tr):<42}")

    print()
    checks = [
        ("inflated peak: the bubble overshoots F", rows[0.0]["peak"] > F * 1.3, f"{rows[0.0]['peak']}"),
        ("trough: disillusionment undershoots F", rows[0.0]["trough"] < F * 0.95, f"{rows[0.0]['trough']}"),
        ("plateau: recovers to ~F", abs(base[-1] - F) < 0.05, f"{base[-1]:.3f}"),
        ("phase order trigger→peak→trough→plateau", peak_t < trough_t < T - 1, f"peak={peak_t}, trough={trough_t}"),
        ("memory damps the bubble (monotone)", all(rows[SWEEP[i]]["amp"] >= rows[SWEEP[i+1]]["amp"] for i in range(len(SWEEP)-1)), "yes"),
        ("full memory -> no bubble (efficient-market limit)", rows[1.0]["amp"] < 0.02, f"{rows[1.0]['amp']}"),
    ]
    ok = True
    for name, good, got in checks:
        ok = ok and good
        print(f"   [{'PASS' if good else 'FAIL'}] {name}  ({got})")
    print(f"\n   → hype amplitude ≈ (1 − memory): {rows[0.0]['amp']} → {rows[0.5]['amp']} → {rows[1.0]['amp']} "
          "as the crowd remembers. A society that all remembers has no bubble — it prices the truth.")
    print(f"\n=== {'PASS' if ok else 'FAIL'}: E7 (Hype Cycle vs memory) ===\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
