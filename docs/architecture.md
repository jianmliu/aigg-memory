# Where aigg-memory sits — the three-layer architecture

> aigg-memory is **auxiliary**: the domain-agnostic cognition/memory kernel (and the
> deterministic lab) whose core functions the **aigg-monopoly** Python simulation calls. This
> page pins aigg-memory's role and the contract the simulation consumes, so the pump town can
> be built against a stable interface without the kernel ever learning the game's vocabulary.

## 1. The three layers

| Layer | Repo | Responsibility | Must NOT |
| --- | --- | --- | --- |
| **Frontend — replay + intervention** | aigg-mud-dev | render & **replay** a run as a MUD; let **external accounts** (humans via telnet/web, outside AI agents via the line protocol) **intervene** in the live world | hold the simulation's truth |
| **Simulation — the pump town** | **aigg-monopoly** (Python) | the reflexive economy world: places, the compute (GCC) market with **endogenous price**, the pump/rumor mechanics, the agents; each agent's cognition = **aigg-memory core calls**. Deterministic + replayable. The compute-price-rumor scenario (`memory_economy_research.md` §8) lives here | reimplement memory |
| **Substrate — cognition kernel + lab** | **aigg-memory** (auxiliary) | give agents memory/reflection/planning, the discernment `q`, **anti-manipulation immunity**, track-record legibility; `examples/eval` is the deterministic lab where the pump-town dynamics (E1–E5) are proven first | **learn "pump" / "GCC"** — stay domain-agnostic |

```
aigg-mud-dev   (frontend: replay + external accounts intervene)
      │  drives / visualizes / injects actions
aigg-monopoly  (Python simulation: pump town + economy + agents)
      │  calls aigg-memory core  (in-process Python, or HTTP)
aigg-memory    (memory / cognition kernel)
```

Both the simulation and the kernel are **Python**, so aigg-monopoly calls the kernel's core
**in-process** (a library import — fast, deterministic, replayable); the **HTTP** surface is the
boundary the *frontend* and *external agents* cross (multiplayer, intervention). Same kernel,
two call styles by layer.

## 2. The contract aigg-monopoly consumes

The three hooks are packaged as a thin, **domain-agnostic** import — `aigg_memory.agent` — so the
simulation calls one stable module in-process (the *same* kernel is on the HTTP surface for the
frontend / external agents). It knows no game vocabulary: `topic`/`marker` are arbitrary strings.

```python
from aigg_memory import agent

# 1) DECISION TIME — read discernment q (believe this call / seize this opp / avoid this trap?)
d = agent.discernment(root, corpus, opp_type, talent=t)   # {q, faculty, social}
#   faculty = a belief I learned myself (E1);  social = a belief a peer warned me with (E2),
#   split by provenance (asserted_by). q = clamp(talent + faculty + social).
if d["q"] <= 0:
    ... engage ...        # else avoid

# 2) SLEEP TIME — consolidate experience
agent.record_episode(root, corpus, slug, outcome, asserted_by=caller)   # the observe-equivalent
agent.sleep(root, corpus, reflector=r, planner=p, now=now)              # reflect -> beliefs, plan
#   (memory.reconcile(root, corpus, judge, now=now, write=True) for called-vs-realized price)

# 3) ALLOCATION / REPUTATION — read a legible track record (H-legibility)
skill = agent.track_record(root, corpus)["skill"]   # self-learned beliefs + evidence depth,
#   from the provenance-stamped, git-versioned history — capital by skill, not by (lucky) wealth.
```

This is not pseudocode: `experiment_hmem.py` (E1) and `experiment_social.py` (E2) drive their
decisions through exactly this `agent` module over the real kernel, reproducing their results.
The decision mapping is one line — `q = clamp(talent + faculty + social)` — and aigg-monopoly
lifts it unchanged.

## 2b. Replay & external intervention (the frontend's two jobs)

- **Replay (复现).** The sim is deterministic (seed + scripted/real cognition) and the memory is
  **git-versioned**, so a whole run reconstructs from `(seed, config)` + the versioned corpora
  (`versioning.restore(ref)`). The frontend re-plays any run exactly, and supports
  counterfactuals (restore to a point, change one input, diverge) — the lab already relies on
  this (E1/E5 are bit-for-bit reproducible).
- **Intervention.** aigg-mud-dev exposes the live world so **external accounts** — humans
  (telnet/web) or outside AI agents (the JSON line protocol) — act *alongside* the sim agents on
  the same rails. Their actions enter the relevant corpus as observations (provenance-stamped to
  the external principal), the sim continues, and the kernel's `allowed-principal` gate governs
  what an outside account may consolidate. This is "live mode": real players can be the
  manipulator, the marks, or the skeptics — and memory's anti-manipulation immunity (E5) is
  tested against *real* adversaries, not only scripted ones.

## 3. The boundary that keeps the kernel clean

**aigg-memory never learns the word "pump" or "GCC."** In E1, `"pump"` was just a string in a
unit's match terms — the kernel stored a typed unit, reflected a belief, stamped provenance, and
answered recall, all without any notion of a market. The pump-town vocabulary (rumor types,
the GCC price, the manipulator, the rug) lives entirely in aigg-monopoly. This buys:

- **Reuse** — other products use the same kernel unchanged.
- **Independence** — the game can change its mechanics without touching the kernel.
- **Safety posture** — memory is the *immune system*; the pump logic sits in the game (a
  simulation / play-money, Monopoly-style game), and the kernel's defensible contribution is the
  anti-manipulation result, never a manipulation tool (see `memory_economy_research.md` §11).

## 4. Lab → product handoff

The pump-town dynamics are de-risked in aigg-memory's deterministic lab first, then implemented
for real in aigg-monopoly:

- **E1 (shipped, `experiment_hmem.py`)** — discernment is *learned*: the avoidance learning
  curve over the real kernel (memory on → rises; off → flat).
- **E5 (`experiment_immunity.py`)** — memory as *anti-manipulation immunity*: rug-rate by memory
  condition, discriminating a manipulator from an honest caller by **provenance / track record**.
- E2 (social discernment over the network), E3 (coordination), E4 (track-record patron) follow.

Each is a deterministic slice that aigg-monopoly can lift once validated. See
[`memory_economy_research.md`](memory_economy_research.md) for the full program and
[`experiment_harness.md`](experiment_harness.md) for the lab's shape. For the concrete wiring —
the turn loop, the hook→experiment map, and the checklist aigg-monopoly follows — see
[`monopoly_integration.md`](monopoly_integration.md).
