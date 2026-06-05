// A minimal TypeScript client for an aigg-memory server.
//   Run the backend:  aigg-memory serve --root ./game-memory --port 8788
// Each NPC gets its own corpus + evidence: npcs/<id>/memory and npcs/<id>/evidence.jsonl.
// No dependencies — uses global fetch (Node 18+, browsers, Deno, Bun).

type Envelope<T> = { ok: boolean; diagnostics: unknown[]; data: T };

export class NpcMemory {
  constructor(
    private baseUrl = "http://localhost:8788",
    private npcId = "default",
    private token?: string,
  ) {}

  private get corpus() { return `npcs/${this.npcId}/memory`; }
  private get evidence() { return `npcs/${this.npcId}/evidence.jsonl`; }

  private async post<T>(path: string, body: object): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
      },
      body: JSON.stringify(body),
    });
    const env = (await res.json()) as Envelope<T>;
    if (!env.ok) throw new Error(`aigg-memory ${path}: ${JSON.stringify(env.diagnostics)}`);
    return env.data;
  }

  /** online: record one observation as the player interacts with the NPC */
  observe(payload: object) {
    return this.post("/memory/observe", { evidence: this.evidence, payload });
  }

  /** online (optional): extract memories from raw dialogue (heuristic, or extractor:"aigg") */
  ingest(transcript: string) {
    return this.post("/memory/ingest", { evidence: this.evidence, transcript });
  }

  /** cheap readiness signal — the app owns the trigger policy */
  shouldSleep(minNew = 5) {
    return this.post<{ pending: number; recommended: boolean }>(
      "/memory/consolidation-status", { evidence: this.evidence, corpus: this.corpus, min_new: minNew });
  }

  /** offline (Dream) — call on the NPC's own trigger (sleep / scene end) */
  sleep() {
    return this.post<{ written: string[] }>(
      "/memory/consolidate", { evidence: this.evidence, corpus: this.corpus, write: true });
  }

  /** online: recall relevant memory for the next interaction (inject bundle into the prompt) */
  recall(query: string, opts: { kinds?: string[]; includeDeps?: boolean;
                                 retriever?: "keyword" | "semantic" | "hybrid" } = {}) {
    return this.post<{ units: any[]; bundle: string; total_in_corpus: number }>(
      "/memory/select", {
        corpus: this.corpus, request: query, kinds: opts.kinds,
        include_deps: opts.includeDeps ?? true, retriever: opts.retriever ?? "semantic",
      });
  }
}

// --- usage in the game loop -------------------------------------------------
// const npc = new NpcMemory("http://localhost:8788", "jiujianxian");
// await npc.observe({ slug: "player_youxia", name: "游侠", kind: "semantic",
//                     description: "论剑后好感升高", match: ["游侠", "好感"], body: "..." });
// if ((await npc.shouldSleep()).recommended) await npc.sleep();
// const { bundle } = await npc.recall("游侠来访");   // -> inject into the NPC's LLM prompt
