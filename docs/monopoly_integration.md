# aigg-monopoly integration — wiring the pump town to the kernel

> The handoff. aigg-monopoly is the **Python pump-town simulation**; it calls aigg-memory's core
> in-process through one module — `aigg_memory.agent` — and gets, for free, every dynamic the lab
> proved (E1–E7). This page is the turn loop, the hook→experiment map, the data model, and a
> checklist. See [`architecture.md`](architecture.md) for the layering and [`memory_economy_research.md`](memory_economy_research.md) for the science.

## 1. What the kernel owns vs what the sim owns

| aigg-monopoly (the sim owns) | aigg-memory (the kernel owns) |
| --- | --- |
| the world: the GCC/asset **price (endogenous/reflexive)**, places, the clock | per-agent **memory**: episodes, beliefs, plans, provenance |
| **action**: buy/sell/join/recruit; the patron's allocation; the `value_source` knob | **discernment `q`** at decision time (recall) |
| the relationship **network** + who-talks-to-whom | **consolidation**: reflect (episodes→beliefs), plan, reconcile |
| roles: prophets / shills / marks / patron | the legible **track record** (provenance + valid-time + git) |
| the pump-town **vocabulary** ("pump", "GCC", "rug") | nothing domain-specific — `topic`/`marker` are strings |

The kernel never learns the game. `from aigg_memory import agent` is the whole surface.

## 2. The turn loop (per tick, per agent)

```python
from aigg_memory import agent

root, corpus = WORLD_ROOT, f"npcs/{a.id}/memory"

# 1) PERCEIVE — the host surfaces this tick's calls / opportunities / traps to agent a.
for opp in opportunities_for(a, now):

    # 2) DECIDE — read discernment q from a's REAL memory (E1 faculty + E2 social warnings;
    #    for a caller, E5 distrust shows up as a "<caller> is a manipulator/pump" belief).
    d = agent.discernment(root, corpus, opp.type, talent=a.talent)   # {q, faculty, social}

    # 3) ACT — the HOST decides & effects the action; the price is reflexive (E7 emerges).
    if d["q"] > FOLLOW_THRESHOLD:
        outcome = host.skip_or_avoid(a, opp)        # discernment says trap -> avoid
    else:
        outcome = host.engage(a, opp)               # buy / follow / join the coalition (E3)

    # 4) OBSERVE — record the realized outcome, provenance-stamped to who made the call.
    agent.record_episode(root, corpus, f"{opp.type}_{now}", outcome.description,
                         match=[opp.type, outcome.tag], asserted_by=opp.caller)

# 5) DIFFUSE — a knower warns / a shill recruits co-located neighbours (E2 defensive / E6 offensive).
for nb in host.neighbours(a):
    if agent.believes(root, corpus, topic, marker="trap"):
        agent.record_episode(root, f"npcs/{nb}/memory", BELIEF, warning_text,
                             match=[topic, "trap"], asserted_by=a.id)   # relayed -> social channel

# 6) SLEEP (periodic, the deep cadence) — reflect episodes -> beliefs (learned + cross-cycle
#    "hype peaks revert" meta-belief, E7), plan intentions, reconcile called-vs-realized price.
agent.sleep(root, corpus, reflector=R, planner=P, now=now)
# memory.reconcile(root, corpus, J, now=now, write=True)  # expectation vs realized -> persist (discovery) or revert (pump)
```

```python
# 7) ALLOCATE (periodic, the patron) — capital by demonstrated skill, not by lucky wealth (E4).
weights = {a.id: agent.track_record(root, f"npcs/{a.id}/memory")["skill"] for a in agents}
host.patron_allocate(budget, weights)   # vs the meritocratic-by-wealth baseline
```

## 2b. The fund asset — NAV oracle + two value flows + audit probes

The pump-town asset is a **fund share**, not the currency (you can't pump the numéraire). A fund
holds a basket of agents and has **two value flows**, each with a failure mode the kernel audits:

| flow | how you profit | failure mode | the probe (host computes from the kernel) |
| --- | --- | --- | --- |
| **traded price** (capital gains) | buy low, sell high; price floats vs NAV | premium **bubble / pump** (E7); a hollow dip (E9) | `premium = price/NAV − 1` |
| **dividend** (income/yield) | hold, collect distributions | a **Ponzi yield** paid from new deposits (E8) | `coverage = NAV/liabilities`, `ponzi_ratio` = share of dividends sourced from `new_deposits` |

The **NAV oracle** is the one new host helper — the fundamental is *what memory computes*:

```python
def nav(root, holdings):                     # NAV = Σ the holdings' memory-computed competence
    return sum(agent.track_record(root, f"npcs/{h}/memory")["skill"] for h in holdings)
```

**Buy/sell decision (extends the turn loop's discernment with the NAV audit):**

```python
nv      = nav(root, fund.holdings)
premium = fund.price / nv - 1                         # E7: inflated vs fundamental
coverage= nv / fund.liabilities                       # E8: solvent / NAV-backed?
manip   = agent.discernment(root, corpus, fund.manager, marker="manipulator")["q"]  # E5
# at a trough (low price) buy ONLY if the NAV is real and materializing (E9), not a hollow pump
buy = (premium < BUY_BELOW and coverage > MIN_COVERAGE and manip == 0
       and host.nav_is_materializing(fund))           # the holdings' production track record is rising
```

**Provenance-tagged dividends (the E8 control):** every distribution the host pays carries its
source — `record_episode(asserted_by=fund.manager, match=[..., source])` with `source ∈
{nav_earnings, new_deposits}`; `memory.reconcile` of *claimed yield vs realized NAV change* exposes
returns funded by new money. A real fund's yield is `nav_earnings`; a Ponzi's is `new_deposits`.

## 3. Hook → experiment map (each is already proven in `examples/eval/`)

| turn-loop hook | client call | dynamic it gives you | lab proof |
| --- | --- | --- | --- |
| decide (own) | `discernment(...).faculty` | discernment is **learned** (a rising curve, not a scalar) | E1 `experiment_hmem.py` |
| decide (social) | `discernment(...).social` | warnings over the network → centrality predicts wealth | E2 `experiment_social.py` |
| decide (caller) | `discernment` / `believes` | refuse the manipulator by track record → **rug-rate capped** | E5 `experiment_immunity.py` |
| diffuse (offensive) | `record_episode(asserted_by=shill)` | a pump cabal percolates; **herd immunity** above a memory threshold | E6 `experiment_pump_immunity.py` |
| act (coalition) | host + `track_record` | venture vs pump is one **value-source** knob, legible only by memory | E3 `experiment_coordination.py` |
| sleep (reconcile) | `memory.reconcile` | called-vs-realized → **persist (discovery) vs revert (pump)**; the **Hype Cycle**, amplitude ≈ (1−memory) | E7 `experiment_hype_cycle.py` |
| allocate (patron) | `track_record(...).skill` | capital by skill ≈ talent oracle ≫ meritocratic | E4 `experiment_legibility.py` |
| price a fund | `premium = price/NAV − 1` (NAV oracle) | premium bubble; at the trough, **read NAV** → buy the real dip, skip the hollow | E9 `experiment_value_trough.py` |
| audit a dividend | `coverage = NAV/liabilities`, payout provenance | a **Ponzi yield** (returns from new deposits) starves under memory | E8 `experiment_ponzi.py` |

## 4. Data model (per agent corpus)

- **episodic** — a recorded outcome ("followed shill, rugged"; "engaged pump, lost"), `asserted_by`
  = who the call came from (provenance), `valid_from` = when.
- **belief** — learned discernment ("`<type>` is a trap"; "`<caller>` is a manipulator"; the
  cross-cycle "hype peaks revert"). `derived_from` the episodes. `asserted_by="self"` (faculty) or
  a peer id (a relayed warning — the social channel).
- **plan** — a forward intention (attend the venture / wait for the plateau), future `valid_from`.
- **goal** — a durable objective the agent plans toward (`locked` if owner-set).
- **fund** (a corpus or unit) — `holdings` (agent ids), `price` (host state), `liabilities`, and a
  provenance-tagged `dividend` ledger (`source ∈ {nav_earnings, new_deposits}`). **NAV is not
  stored** — it is *derived* on demand from the holdings' track records (the NAV oracle, §2b), so
  it can't be faked; `premium` and `coverage` are computed from it.
- The whole corpus is **git-versioned** → replay + the auditable track record.

## 5. Checklist for aigg-monopoly

1. `from aigg_memory import agent` — the only kernel import in the hot path.
2. one corpus per agent: `npcs/<id>/memory` under one world root.
3. wire the §2 turn loop; the host owns the reflexive **share price**, the action, the network, the
   clock, and the `value_source` knob; the kernel owns `q`, beliefs, plans, the track record.
4. the asset is a **fund share** (§2b): derive `NAV` from the holdings' track records (never store
   it), compute `premium`/`coverage` from it, and tag every dividend with its source — the two
   value flows (price → E7/E9, dividend → E8) with their two audits.
5. seed the host RNG and stamp `now` from the world clock (the kernel ships no clock) →
   **deterministic + replayable** (commit each agent/fund corpus per tick; `versioning.restore(ref)`).
6. measurement reads the store, never the loop: rug-rate, centrality→wealth, hype amplitude,
   realized-talent, premium, coverage — the same probes the lab uses (`examples/eval/` E1–E9).
7. **boundary & ethics:** the kernel never learns "pump"/"GCC"; the sim is **play-money,
   simulation-only**; the build target is the immune system (E5/E6) and an honest price
   (E7/discovery), never a manipulation tool. Real human/agent accounts may intervene via the
   `aigg-mud-dev` frontend, provenance-stamped and `allowed-principal`-gated.

## 6. The one-paragraph handoff

> aigg-monopoly imports `aigg_memory.agent`, gives every NPC a corpus, and runs the 7-step loop:
> perceive → **discernment q** → host acts (reflexive price) → **record outcome** → diffuse →
> **sleep (reflect/plan/reconcile)** → **patron allocates by track record**. Out of that loop the
> lab's results re-emerge in a live world — learned discernment (E1), social warnings (E2),
> venture-vs-pump legibility (E3), skill-bankable capital (E4), individual & herd immunity
> (E5/E6), and the Hype Cycle damped by memory (E7) — with no pump-town vocabulary ever entering
> the kernel. The science is done and reproducible; this is the wiring.
