# examples/eval — the behavioral-eval harness (MVP)

A runnable, deterministic implementation of [`docs/experiment_harness.md`](../../docs/experiment_harness.md):
the generic runner + a starter probe/verb library + a world adapter, so a new experiment is a
**manifest**, not a script.

```bash
python3 examples/eval/run.py examples/eval/experiments/memory_correctness_reconcile.json
python3 examples/eval/run.py examples/eval/experiments/mud_coordination_party.json
python3 examples/eval/run.py examples/eval/experiments/information_diffusion.json
python3 examples/eval/run.py examples/eval/experiments/relationship_formation.json
python3 examples/eval/run.py examples/eval/experiments/mud_spacetime_party.json
python3 examples/eval/run.py examples/eval/smallville.py          # 25 agents, generated
python3 examples/eval/experiment_hmem.py                          # E1: discernment learning curve
python3 examples/eval/experiment_immunity.py                     # E5: anti-manipulation immunity
python3 examples/eval/experiment_social.py                       # E2: social discernment / centrality
python3 examples/eval/experiment_pump_immunity.py                # E6: pump cabal vs herd immunity
python3 examples/eval/experiment_coordination.py                 # E3: venture vs pump = one knob
python3 examples/eval/experiment_hype_cycle.py                    # E7: the Hype Cycle vs memory
python3 examples/eval/experiment_legibility.py                    # E4: capital by track record
python3 examples/eval/experiment_ponzi.py                         # E8: Ponzi fund vs memory
python3 examples/eval/experiment_value_trough.py                  # E9: real value vs hollow at the trough
```

An experiment file may be JSON (a static manifest) or a `.py` generator exposing `build()` —
at 25 agents you generate the hundreds of steps from compact config rather than hand-writing
them.

The last three reproduce Generative Agents' **three emergent behaviors** as configuration on
the `mud` adapter — same runner, different manifests:

| experiment | emergence | what it shows (all measured from the store) |
| --- | --- | --- |
| `mud_coordination_party` | **coordination** | host plans → invites diffuse → guests intend; a believable subset; a time-change replans every dependent plan (reconcile + stale) |
| `information_diffusion` | **information diffusion** | a rumor relays `sam→tom→jen→dan`; every copy traces to a teller who knew it; cutting one hop strands the chain |
| `relationship_formation` | **relationship formation** | encounters accrue `person_<id>` edges (network density), then `reflect` synthesizes a relationship belief; dropping a meeting drops the edge and the belief |
| `mud_spacetime_party` | **coordination, in space+time** | World (`move`/places) + Time (`tick`/`sleep`) rails: the invite diffuses only by **co-location**, intentions form only for those who learned, attendance needs being at the right **place at the right time** — the funnel `knew 3 > intended 2 > showed 1` emerges; a never-co-located NPC is simply left out |

It needs **no real model and no network** — it starts a real `aigg-memory serve` and a tiny
**scripted stub model** (an OpenAI-compatible endpoint that replies from manifest rules), both
on localhost, then drives the cognition-under-test (plan / reconcile / reflect) over HTTP and
measures by reading the store files. Deterministic: same manifest → same verdict, every run.
Exits non-zero on failure (CI-friendly).

## Layout (mirrors the design's layering)

| file | role |
| --- | --- |
| `harness.py` | the generic, experiment-blind **runner** + `serve` subprocess + scripted **stub model** + the `Ctx` handed to verbs/probes |
| `verbs.py` | **verb** library — reusable host actions (store-setup `fact`/`goal`/`unit`; cognition `plan`/`reconcile`/`reflect`) |
| `probes.py` | **probe** library — read-only measurements over the corpora (`unit_status`/`unit_field`/`derived_from`/…) |
| `experiments/*.json` | **manifests** — pure data: `world`, `model_script`, `seed`, `steps`, `probes` (+ `expect`), `ablations` |
| `run.py` | entrypoint — runs the full condition + ablations, prints a report, sets the exit code |

## Adding an experiment

1. Write a manifest (data). 2. If you need a new measurement or action, add **one** probe to
`probes.py` or **one** verb to `verbs.py` — reusable by every later manifest. Nothing else
changes; the runner is shared.

## The first experiment: memory correctness

`memory_correctness_reconcile.json` validates a property the paper's append-only memory stream
could not have: when a supporting fact is superseded (the user moved Shanghai → Beijing),
`reconcile` archives the old fact with valid-time **and** stale-propagation flags the dependent
plan — with zero bespoke invalidation code. The `no_reconcile` ablation removes the step and the
runner asserts both outcomes **flip**, demonstrating the mechanism's necessity (the same
ablation method the paper used for believability, here on memory correctness, run as an exact
git-style re-run with diffed probe values).

## The mud sandbox: coordination by configuration

`mud_coordination_party.json` is Generative Agents' **coordination** emergence (Isabella's
Valentine party) expressed as config on the `mud` adapter — multiple NPCs, one corpus each.
The rails (`invite`/`announce_change` verbs) relay information with provenance; the cognition
(`plan`/`reconcile`) is the real kernel over HTTP; the multi-corpus probes measure from the
stores:

- `host_planned` — Isabella forms her party plan (real `/memory/plan`).
- `knew = 4` — **information diffusion**: every NPC learns about the party (via the relay).
- `intended = 2` — a *believable subset* form an attend-plan (one guest knows but doesn't).
- `stale_replan = 2` — when Isabella moves the time, `reconcile` + stale-propagation flag every
  dependent attend-plan **across NPCs** for replan, with zero bespoke code.
- `provenance = true` — every invite traces back to Isabella (earned, not hallucinated).

The `no_reconcile` ablation flips `stale_replan` to 0 (guests would show at the stale time).

## What's next (per the design doc)

## Scale: 25-agent Smallville + an ablation matrix

`smallville.py` generates a 25-agent / 12-tick run from compact config (seeded, so it replays
identically): each tick agents move to places and co-located pairs `meet` (network forms) and
sometimes gossip a single seeded rumor (`converse` + the conditional `relay`). It reproduces
the paper's headline figures and prints an ablation matrix:

```
   probe      full     no_conversation  no_encounters
   knew       12       1                12              # diffusion 1/25 -> 12/25 (~48%, paper ~48%)
   traceable  True     True             True            # every knower learned from a knower
   density    0.3833   0.3833           0.0             # network density (paper 0.167 -> ~0.74)
```

Cut conversation → the rumor never leaves its origin (knew 12→1); cut encounters → no network
(density →0). Same runner, a generator instead of a static manifest.

## E1 — discernment is *learned* (the economics-of-memory research)

`experiment_hmem.py` is the first experiment of [`docs/memory_economy_research.md`](../../docs/memory_economy_research.md)
(H-mem, the truthful-signal slice of the fund-share scenario). A closed loop: each
round a recurring trap ("pump") appears; the agent's discernment is read from its **real**
aigg-memory (does recall surface a "pump is a trap" belief?); after a couple of burns a
`reflect` pass consolidates the episodes into that belief, and thereafter the agent avoids.

```
memory ON   avoidance(pump) per round: [0, 0, 1, 1, 1, 1, 1, 1]   burns=2   real-engaged=8/8
memory OFF  avoidance(pump) per round: [0, 0, 0, 0, 0, 0, 0, 0]   burns=8   real-engaged=8/8
```

Discernment **rises** with memory (a learning curve a static `faculty` scalar can't produce)
and is **flat** without (reflect off → no belief → burned every round); the agent stays
selective (keeps engaging the genuine opportunity, 8/8). Memory's value here = 6 burns avoided.

`experiment_immunity.py` is **E5 — memory as anti-manipulation immunity** (the *manipulated*
slice). Two callers distinguished by **provenance**: a `shill` whose every "price will moon"
call is a pump that rugs followers, and an honest `oracle`. The agent follows a caller unless
recall surfaces a "this caller's calls are pumps" belief; after a couple of rugs, `reflect`
forms that per-caller belief and the agent skips the shill — *but keeps following the oracle*.

```
memory ON   rugged-by-shill=2/8   honest-caller-followed=8/8
memory OFF  rugged-by-shill=8/8   honest-caller-followed=8/8
```

Memory **caps the rug-rate** (2 vs 8) and **discriminates the manipulator from the honest
caller by track record** — it doesn't become paranoid. This is provenance + reflection + recall
doing what an append-only memory stream cannot, and it is the *inverse* of a pump tool.

`experiment_social.py` is **E2 — H-social** (shared discernment). One agent's "pump is a trap"
belief diffuses over the **relationship network** (a friend warns a friend, provenance-stamped),
so an agent avoids a trap it never personally hit. Network **centrality** then predicts wealth —
but only because the network carries the warnings:

```
network ON   ρ(wealth,centrality)=+0.995   origin(burns=0) hub(0) leaf(1) isolated(6)
network OFF  ρ(wealth,centrality)=+0.280   origin(0) hub(6) leaf(6) isolated(6)
```

Social capital is a real, independent success axis — and a *purely instrumental* one: cut the
warning flow (same network) and centrality predicts almost nothing.

`experiment_pump_immunity.py` is **E6 — the pump cabal vs herd immunity** (E2's dual: the same
network, but spreading "buy + recruit" instead of a warning — negative-sum, *earlier = more
profit*). A follower must be a mark (no memory); a memory-equipped agent (E5) refuses and won't
relay, so the pump is a percolation on the memoryless sub-network. As memory penetration rises,
reach collapses at the percolation threshold:

```
   mem%  recruited  marks_rugged  manip_profit
     0%       599          535          535        # naive society: the pump recruits ~everyone
    70%       111          108          108
    80%         8            5            5        # past the threshold (~1-1/⟨k⟩): the pump dies
```

A society that remembers can't be pumped — there are no marks. Memory's immunity is not only
individual (E5) but **herd-level**, and the *same* `ρ(wealth, earliness)` that looks like
"social capital pays" can be *earned* (E2, welfare↑) or *extracted* (E6, welfare↓) — you can
only tell by the recipients' sign.

`experiment_coordination.py` is **E3 (unified)** — resolving "isn't a coalition just a group
pump?" The coordination machinery is identical; a *productive venture* and a *pump cabal* differ
only by the **value source** (an external beneficiary paid for value → counterparty welfare +;
a transfer from recruited marks → counterparty welfare −), and only **memory** can read it:

```
condition     ρ(wealth,coord)   counterparty welfare   pump profit
memory OFF        +1.000               -1.0                274        # coordination always pays
memory ON         +0.639             +273.0                  0        # pumps starve; ventures remain
```

`ρ(wealth, coordination)` is +1.0 either way — wealth can't distinguish them. `track_record`
(the counterparty-welfare sign of a leader's history) can: with memory, members refuse leaders
whose past harmed counterparties → pumps can't assemble, total welfare flips positive, and
coordination pays *only if it creates value*.

`experiment_hype_cycle.py` is **E7 — the Gartner Hype Cycle as reflexive belief's waveform, and
memory as its damper.** An inflated expectation diffuses (overshoot → Peak), reality `reconcile`s
it (revert → Trough), `reflect` finds the true value (→ Plateau). The price trace is the curve:

```
memory  0%:  ▄▄▄▄▄▄▄▄▄▅▅▆▇▇██████▁▂▂▃▃▃▃▃▃▃▃▄▄▄▄▄▄▄▄▄   peak 1.99 → trough 0.40 → plateau 1.00
```

A memory-equipped agent has seen past cycles and doesn't buy the top, so the bubble **amplitude
shrinks ~ (1 − memory)**: 0.986 → 0.50 → 0.0. A society that all remembers has no bubble — it
prices the truth (the efficient-market limit). Memory's third role: not just blocking pumps (E6)
or rewarding discovery, but **damping the hype cycle itself**.

`experiment_legibility.py` is **E4 — H-legibility** (capital by memory track record, not by lucky
wealth). In Talent-vs-Luck the richest are often the luckiest; a patron allocating "meritocratically"
by current wealth rewards luck. A memory `track_record` is a luck-*filtered* skill signal (the traps
an agent learned to recognize — skill earns it, luck can't), so allocating by it tracks true skill:

```
patron policy   realized-talent ρ(wealth,skill)   Gini
talent                    +0.710                  0.297   (oracle upper bound)
track_record              +0.703                  0.298   ← memory: ~matches the oracle
meritocratic              +0.493                  0.328   (rewards luck, entrenches it)
```

Meritocracy can't tell "won" from "got lucky"; the track record can — so it allocates by skill, not
luck. **Memory makes skill bankable.**

`experiment_ponzi.py` is **E8 — the Ponzi fund vs memory** (E6 re-anchored onto a fund). A Ponzi
pays "returns" from new deposits, not NAV; its **coverage ratio** (NAV/liabilities) is < 1 from
launch, hidden by fresh money. A memory-equipped investor audits the *source of returns* (NAV vs
new deposits; the manager's track record) and refuses — so the Ponzi recruits only the unaudited
minority:

```
memory   lifespan  marks   fraud haul   coverage start→collapse
   0%       19      1000     200.0       0.80 → 0.01
  80%       14       200      40.0       0.80 → 0.01
```

Its reach falls ~ (1 − memory): haul 200 → 40, victims 1000 → 200, coverage insolvent throughout.
A Ponzi needs darkness; auditing the source of returns is the control. Memory is light.

`experiment_value_trough.py` is **E9 — real value and hollow hype share one curve; memory tells
them apart at the trough.** A genuinely valuable fund's NAV materializes *late*, so its price
overshoots (Peak), drops below NAV (Trough), then recovers to a high plateau — the *same* curve a
hollow pump traces, except the pump's NAV never materializes and it dies at the bottom. At the
peak and the trough they're **indistinguishable by price** (both 0.30 at the trough); only the
NAV differs (0.87 vs 0.05):

```
price (real):   ▃▄▄▅▅▆▆▆▇▇███▇▆▅▄▃▂▁▁▁▁▁▂▂▂▂▃▃▃▃▄▄▄▄▅▅▅▆
price (hollow): ▄▄▅▅▆▆▆▇▇▇████▇▆▅▄▃▂▂▂▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁▁   ← identical until the trough, then diverge
strategy            return
memory (audit NAV)    6.0   buy all dips  4.5 (rugged)   avoid all crashes  0.0 (missed it)
```

The hype cycle is **not a fraud signal** — real value troughs too. It's to be *read* at the
trough: "buy the dip" is alpha on real NAV and suicide on a hollow one, and the NAV audit (memory)
is the difference. Memory is the value investor's edge — it inverts the crowd's buy-high/sell-low.

## Real-model validation (the `--real` switch)

By default the kernel-driven experiments stub the LLM (scripted JSON) so the mechanics and
aggregate dynamics are **deterministic** (CI-able). The `--real` switch routes those LLM steps
to a **real cheap model** (`claude -p`, `haiku`) instead — to spot-check that the architecture
holds with a real, noisy judge:

```bash
python3 examples/eval/run.py examples/eval/experiments/mud_coordination_party.json --real
AIGG_EVAL_REAL=1 python3 examples/eval/experiment_hmem.py        # closed-loop scripts read the env
```

Two backends via `AIGG_EVAL_BACKEND`:

```bash
# claude-cli (default): claude -p, the cheap model (haiku); subscription auth, budget-capped
python3 examples/eval/run.py <manifest> --real

# ollama (free, local, reliable): Ollama's OpenAI-compatible endpoint — recommended for evals
AIGG_EVAL_REAL=1 AIGG_EVAL_BACKEND=ollama AIGG_EVAL_MODEL=gemma4:latest python3 examples/eval/experiment_hmem.py
```

Ollama is the better eval backend: free, fast, no `claude -p` agentic-persona issue (a plain
OpenAI-compatible call follows "return only JSON"), and no plugin-hook recursion. **E1 and E5
`--real` over `ollama/gemma4` each pass 3/3** — every run synthesizes a *differently-worded*
belief (`avoidance_of_scams`, `negative_consequence_of_following_shill`, … several without the
keywords at all), and **provenance mode catches every one** via its evidence → the outcomes are
deterministic (`[0,0,1,1,1,1,1,1]`; rugged 2/8) despite non-deterministic wording. So Ollama gives
the reliability and provenance mode gives the wording-robustness.

Budget-guarded by construction: `AIGG_EVAL_MAX_CALLS` (default 32) hard-caps calls; ablations are
skipped in real mode; for claude-cli, `AIGG_MEMORY_REENTRY=1` is set so the plugin's session hooks
don't recurse. Knobs: `AIGG_EVAL_BACKEND`, `AIGG_EVAL_MODEL`, `AIGG_EVAL_OLLAMA_URL`,
`AIGG_EVAL_MAX_CALLS`, `AIGG_EVAL_TIMEOUT` (the LLM-call timeout — local big models can be slow to
(re)load; the kernel's `/memory/{reflect,reconcile,plan}` now take a per-request `timeout`).

**What reproduces over a real model, and what doesn't.** Single-step ops reproduce reliably:
`reflect` forming a belief from episodes (E1/E5) passes 3/3 over `ollama/gemma4` — the wording
varies but `provenance` mode reads the evidence. **Multi-step causal chains are brittle**, though:
running `mud_coordination_party --real`, `plan`/`reconcile` execute (6 calls, no errors) and
diffusion passes, but the coordination chain breaks — the cheap model writes a *plausible* attend
plan yet cites `derived_from=['goal_socialize']` and omits the `invite_party` it was reacting to,
so when `reconcile` later archives the invite, the plan isn't flagged `stale` (`stale_replan=0`).
A real cheap model produces causally-incomplete provenance; the **deterministic stub remains the
source of truth for the full coordination dynamics**, while `--real` validates that the ops run
and the simple dynamics hold.

**It's a spot-check, not a gate.** A real model's `reflect`/`reconcile` judgments are
*non-deterministic*, so the deterministic pass-criteria (designed for the stub — e.g. a keyword
`believes()` check) may flake on wording the model varies. `experiment_hmem_real.py` is the
minimal in-process proof that it *can* hold: one `reflect` over haiku synthesizes the "pump is a
trap" belief (provenance back to the burn episodes) → `believes(...)=True`, `q=1.0`.

**Finding (kernel fix surfaced by this):** `claude -p` is the *agentic* Claude Code, not a raw
completion endpoint — with `--append-system-prompt` it replies conversationally and ignores
"return only JSON". The claude-cli backend now uses `--system-prompt` (override) +
`--exclude-dynamic-system-prompt-sections`, making it a clean structured extractor.

### The three discernment modes (why a real model flaked, and the fix)

A real model's `reflect` chooses its *own wording* for a belief ("victimized by pump schemes",
"deceptive offer patterns") — so the decision layer can't rely on the exact keywords the stub
guarantees. `agent.believes` / `discernment` take a `mode`:

| mode | how it decides "is this belief about X" | wording-robust | needs LLM | needs embedding |
| --- | --- | --- | --- | --- |
| `text` (default) | substring match on the belief's own text | ✗ (brittle) | ✗ | ✗ |
| (semantic) | cosine of a query vs the belief, real embedder | ~ (query-dependent; a 2-word query scored a reworded belief only 0.135) | ✗ | ✓ (torch) |
| **`provenance`** | the belief is **`derived_from`** evidence about X | **✓** | ✗ | ✗ |

`provenance` is the robust, deterministic, no-LLM/no-embedding fix: a belief is *what its
evidence is*, whatever words the synthesis chose. E1's decision uses it, so `--real` reproduces
the learning curve whenever the cheap model returns a valid belief (its residual flakiness is
model *reliability* — a small model occasionally emits invalid structured output — not wording).

## What's next (per the design doc)

All three emergences pass deterministically — small (`mud_*`) and at scale (`smallville.py`),
each with ablations; E1 shows discernment is learned. Next: E2 (social discernment over the
network), E5 (memory as anti-manipulation immunity — the rug-rate study), then **live mode**
(a real host LLM sharing the identical rails) — see
[`docs/mud_sandbox_design.md`](../../docs/mud_sandbox_design.md) and
[`docs/memory_economy_research.md`](../../docs/memory_economy_research.md).
