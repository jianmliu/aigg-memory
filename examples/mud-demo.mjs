// Minimal RUNNABLE Node demo: a MUD where EACH NPC has its own aigg-memory + dream.
//
//   terminal 1:  aigg-memory serve --root ./game-memory --port 8788
//   terminal 2:  node examples/mud-demo.mjs
//
// No `npm install` — Node 18+ has global fetch. Override the URL with AIGG_MEMORY_URL.
// Each NPC is a separate corpus (npcs/<id>/memory) + evidence file, so memories never
// cross between NPCs. Per NPC: observe → readiness → dream (sleep) → recall.

const BASE = process.env.AIGG_MEMORY_URL ?? "http://localhost:8788";

async function call(path, body) {
  const res = await fetch(BASE + path, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  });
  const env = await res.json();
  if (!env.ok) throw new Error(`${path}: ${JSON.stringify(env.diagnostics)}`);
  return env.data;
}

// one NPC's memory, scoped to its own corpus + evidence
function npc(id) {
  const corpus = `npcs/${id}/memory`, evidence = `npcs/${id}/evidence.jsonl`;
  return {
    observe: (payload) => call("/memory/observe", { evidence, payload }),
    status: () => call("/memory/consolidation-status", { evidence, corpus, min_new: 1 }),
    // the NPC sleeps -> the full Dream pass for THIS npc (consolidate + reconcile; the
    // LLM steps run if the server has a model — pass aigg_url/backend to enable them).
    dream: (deep = false) => call("/memory/dream", { evidence, corpus, write: true, min_count: 1, deep }),
    recall: (q) => call("/memory/select", { corpus, request: q, retriever: "semantic", include_deps: true }),
  };
}

try {
  const health = await fetch(BASE + "/healthz").then((r) => r.json());
  console.log(`connected to aigg-memory at ${BASE}  (root: ${health.data.root})\n`);

  // two NPCs living in the same world, each remembering different things
  const sage = npc("sage"), smith = npc("smith");

  console.log("→ the player visits each NPC (observe, per-NPC evidence)");
  for (let i = 0; i < 2; i++) {
    await sage.observe({ slug: "player_youxia", name: "游侠", kind: "semantic",
      description: "游侠论剑后好感升高", match: ["游侠", "好感", "visitor"],
      body: "游侠初见好奇剑法;再访论剑,好感升到高位。", deps: ["concept_swordsmanship"] });
    await sage.observe({ slug: "concept_swordsmanship", name: "剑法", kind: "procedural",
      description: "剑意源于心,醉中悟剑", match: ["剑法", "swordsmanship"], body: "1. 静心  2. 观剑  3. 醉而忘形" });
    await smith.observe({ slug: "player_owes_gold", name: "欠款", kind: "episodic",
      description: "游侠赊了一把剑,欠 50 金", match: ["欠款", "gold", "游侠"], body: "The hero bought a sword on credit: 50 gold owed." });
  }

  // each NPC sleeps on its own trigger -> Dream consolidates ITS memory only
  for (const [name, who] of [["sage", sage], ["smith", smith]]) {
    const st = await who.status();
    if (st.recommended) {
      const d = await who.dream(/* deep */ false);
      console.log(`→ ${name} sleeps (dream): wrote ${d.consolidated.written.length} unit(s)`);
    }
  }

  // recall is per-NPC: the smith doesn't know swordsmanship, the sage doesn't know the debt
  console.log(`\n→ sage recalls "游侠来访":`);
  for (const u of (await sage.recall("游侠来访")).units)
    console.log(`   • ${u.name} [${u.kind}]: ${u.description}${u.apply ? `  — ${u.apply}` : ""}`);
  console.log(`→ smith recalls "游侠 欠款":`);
  for (const u of (await smith.recall("游侠 欠款")).units)
    console.log(`   • ${u.name} [${u.kind}]: ${u.description}`);

  console.log(`\nEach NPC kept its own memory (npcs/<id>/memory) and dreamt independently.`);
} catch (err) {
  console.error(`\n✗ ${err.message}\n  is the server running?  aigg-memory serve --root ./game-memory --port 8788`);
  process.exit(1);
}
