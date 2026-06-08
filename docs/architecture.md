# Where aigg-memory sits — the three-layer architecture

> aigg-memory is **auxiliary**: the domain-agnostic cognition/memory substrate (and the
> deterministic lab) beneath the **aigg-monopoly** "pump town" product. This page pins
> aigg-memory's role and the contract aigg-monopoly consumes, so the product can be built
> against a stable interface without the kernel ever learning the game's vocabulary.

## 1. The three layers

| Layer | Repo | Responsibility | Must NOT |
| --- | --- | --- | --- |
| **Product — the pump town** | **aigg-monopoly** (primary) | the reflexive economy world: places, the compute (GCC) market with **endogenous price**, the pump/rumor mechanics, players, the Monopoly-style capital/luck dynamics. The compute-price-rumor scenario (`memory_economy_research.md` §8) lives here. | — |
| **Engine — economy + research** | aigg-mud-demo *(the dev/reference demo)* | the gamekit STF (`applyTx`), the Effort-Luck-Choice economy, the talent-vs-luck / faculty-benchmark experiments, the reference MUD | hold players' long-term memory |
| **Substrate — cognition + lab** | **aigg-memory** (auxiliary) | give agents memory/reflection/planning, the discernment `q`, **anti-manipulation immunity**, track-record legibility; `examples/eval` is the deterministic lab where the pump-town dynamics (E1–E5) are proven before they ship in the product | **learn "pump" / "GCC"** — stay domain-agnostic |

```
aigg-monopoly  (pump town = product)
   ├── economy / STF + experiments   ← aigg-mud-demo (gamekit)
   └── cognition / memory            ← aigg-memory  (HTTP)
```

## 2. The contract aigg-monopoly consumes

aigg-monopoly drives players; at three points each turn it calls aigg-memory over its public
HTTP surface (no kernel code in the product, no product code in the kernel):

- **Decision time — read discernment `q`** (do I believe this call / seize this opp / avoid this
  trap?):
  ```
  facultyFromMemory(playerCorpus, oppType) -> number   # POST /memory/select : is there an
  socialWarning(playerCorpus, oppType)     -> number   #   active "<type> is a trap" belief,
                                                        #   mine or a neighbour's (diffused)?
  ```
- **Sleep time — consolidate experience:**
  ```
  POST /memory/observe   # record the outcome of an engagement (an episode)
  POST /memory/reflect   # episodes -> a "<type>/<caller> is a trap" belief  (learned discernment)
  POST /memory/plan      # goals+beliefs -> intentions (metabolic foresight; don't act when broke)
  POST /memory/reconcile # a called price vs the realized price; correct stale beliefs
  ```
- **Allocation / reputation — read a legible track record** (the patron / capital-allocation
  lever, H-legibility):
  ```
  trackRecord(playerCorpus) -> skillEstimate   # the versioned, provenance-stamped avoidance
                                               # history (timeline / units) — skill made legible
  ```

The mapping is one line in the product's decision step (as proven in `examples/eval/experiment_hmem.py`):
`q = clamp(talent + facultyFromMemory(corpus, type) + socialWarning(corpus, type))`.

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
[`experiment_harness.md`](experiment_harness.md) for the lab's shape.
