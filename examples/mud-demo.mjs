// Minimal RUNNABLE Node demo against a live aigg-memory server.
//
//   terminal 1:  aigg-memory serve --root ./game-memory --port 8788
//   terminal 2:  node examples/mud-demo.mjs
//
// No `npm install` — Node 18+ has global fetch. Override the URL with
// AIGG_MEMORY_URL. Walks the NPC memory loop: observe → status → sleep → recall.

const BASE = process.env.AIGG_MEMORY_URL ?? "http://localhost:8788";
const NPC = "jiujianxian";
const corpus = `npcs/${NPC}/memory`;
const evidence = `npcs/${NPC}/evidence.jsonl`;

async function call(path, body) {
  const res = await fetch(BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const env = await res.json();
  if (!env.ok) throw new Error(`${path}: ${JSON.stringify(env.diagnostics)}`);
  return env.data;
}

const observe = (payload) => call("/memory/observe", { evidence, payload });

try {
  const health = await fetch(BASE + "/healthz").then((r) => r.json());
  console.log(`connected to aigg-memory at ${BASE}  (root: ${health.data.root})\n`);

  // 1) the player chats with the NPC — two interactions → two observations each
  console.log("→ observe: the player talks to the NPC");
  for (let i = 0; i < 2; i++) {
    await observe({
      slug: "player_youxia", name: "游侠", kind: "semantic",
      description: "游侠论剑后好感升高", match: ["游侠", "好感", "visitor"],
      body: "游侠初见好奇剑法;再访论剑,好感升到高位。",
      deps: ["concept_swordsmanship"],
    });
    await observe({
      slug: "concept_swordsmanship", name: "剑法", kind: "procedural",
      description: "剑意源于心,醉中悟剑", match: ["剑法", "swordsmanship"],
      body: "1. 静心  2. 观剑  3. 醉而忘形",
    });
  }

  // 2) is it time to consolidate? (the app owns the trigger)
  const status = await call("/memory/consolidation-status", { evidence, corpus, min_new: 1 });
  console.log(`→ status: ${status.pending} pending, recommended=${status.recommended}`);

  // 3) the NPC sleeps → Dream consolidation writes typed memory
  if (status.recommended) {
    const result = await call("/memory/consolidate", { evidence, corpus, write: true });
    console.log(`→ sleep: wrote ${result.written.length} unit(s): ${result.written.join(", ")}`);
  }

  // 4) the player returns → recall context (semantic + dependency-aware)
  const ctx = await call("/memory/select", { corpus, request: "游侠来访", retriever: "semantic", include_deps: true });
  console.log(`\n→ recall "游侠来访":`);
  for (const u of ctx.units) {
    const tag = u.relation === "dependency" ? "↳ dependency" : `score ${u.score}`;
    console.log(`   • ${u.name} [${u.kind}] (${tag}): ${u.description}`);
  }
  console.log(`\ncontext bundle to inject into the NPC prompt:\n${ctx.bundle}`);
} catch (err) {
  console.error(`\n✗ ${err.message}\n  is the server running?  aigg-memory serve --root ./game-memory --port 8788`);
  process.exit(1);
}
