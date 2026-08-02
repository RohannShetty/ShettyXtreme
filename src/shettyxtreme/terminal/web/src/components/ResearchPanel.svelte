<script lang="ts">
  import { onMount } from "svelte";
  import { get, post, postBody } from "../lib/api";
  import { onMessage } from "../lib/ws";
  import ResearchBriefDetail from "./ResearchBriefDetail.svelte";
  import { Button } from "$lib/components/ui/button";
  import { Badge } from "$lib/components/ui/badge";
  import { Checkbox } from "$lib/components/ui/checkbox";
  import { Textarea } from "$lib/components/ui/textarea";
  import { RotateCw } from "@lucide/svelte";
  import type {
    ResearchBrief,
    ResearchBriefListResponse,
    ResearchDecisionResponse,
    ResearchLens,
    ResearchRunResponse,
    ResearchToolDef,
  } from "../lib/api";

  let lenses: ResearchLens[] = $state([]);
  let tools: ResearchToolDef[] = $state([]);
  let briefs: ResearchBrief[] = $state([]);
  let selected: ResearchBrief | null = $state(null);
  let selectedId = $state("");
  let selectedLenses = $state<string[]>([]);
  let selectedTools = $state<string[]>([]);
  let contextText = $state("");
  let running = $state(false);
  let runChips: { lens: string; ok: boolean; error: string }[] = $state([]);
  let statusFilter = $state("All");
  let lensFilter = $state("All");
  let error = $state("");
  let deciding = $state(false);

  const statuses = ["All", "Proposed", "Approved", "Rejected"];

  onMount(() => {
    loadAll();
    const offNew = onMessage("research", (data) => {
      const ev = data as { event: string; data: unknown };
      if (ev.event === "new_brief") {
        const brief = ev.data as ResearchBrief;
        briefs = [brief, ...briefs.filter((b) => b.brief_id !== brief.brief_id)];
        if (!selectedId) {
          selectedId = brief.brief_id;
          selected = brief;
        }
      } else if (ev.event === "decision") {
        const d = ev.data as { brief_id: string; status: string };
        briefs = briefs.map((b) =>
          b.brief_id === d.brief_id ? { ...b, status: d.status, decided_at: new Date().toISOString() } : b,
        );
        if (selected && selected.brief_id === d.brief_id) selected = { ...selected, status: d.status };
      }
    });
    return offNew;
  });

  async function loadAll(): Promise<void> {
    error = "";
    try {
      const [l, t, b] = await Promise.all([
        get<{ lenses: ResearchLens[] }>("/api/research/lenses"),
        get<{ tools: ResearchToolDef[] }>("/api/research/tools"),
        get<ResearchBriefListResponse>("/api/research/briefs"),
      ]);
      lenses = l.lenses;
      if (selectedLenses.length === 0) selectedLenses = l.lenses.map((x) => x.name);
      tools = t.tools;
      briefs = b.briefs;
      if (!selectedId && briefs.length > 0) {
        selectedId = briefs[0].brief_id;
        selected = briefs[0];
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function run(): Promise<void> {
    if (running) return;
    running = true;
    runChips = [];
    error = "";
    try {
      const resp = await postBody<ResearchRunResponse>("/api/research/run", {
        lenses: selectedLenses,
        tools: selectedTools.length > 0 ? selectedTools : null,
        context: contextText ? { operator: contextText } : null,
      });
      runChips = resp.results.map((r) => ({
        lens: r.lens,
        ok: r.error === null && r.brief !== null,
        error: r.error ?? "",
      }));
      await loadAll();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      running = false;
    }
  }

  function select(id: string): void {
    selectedId = id;
    selected = briefs.find((b) => b.brief_id === id) ?? null;
  }

  function toggleTool(name: string): void {
    selectedTools = selectedTools.includes(name)
      ? selectedTools.filter((t) => t !== name)
      : [...selectedTools, name];
  }

  async function onDecide(status: "approved" | "rejected"): Promise<void> {
    if (!selected || deciding || selected.status !== "proposed" || selected.expired) return;
    deciding = true;
    error = "";
    try {
      const action = status === "approved" ? "approve" : "reject";
      const resp = await post<ResearchDecisionResponse>(
        `/api/research/briefs/${selected.brief_id}/${action}`,
      );
      briefs = briefs.map((b) =>
        b.brief_id === resp.brief_id ? { ...b, status: resp.status } : b,
      );
      if (selected.brief_id === resp.brief_id) selected = { ...selected, status: resp.status };
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
      await loadAll();
    } finally {
      deciding = false;
    }
  }

  function dirBadgeClass(direction: number): string {
    return direction === 1 ? "price-up" : direction === -1 ? "price-down" : "dir-flat";
  }

  function dirLabel(direction: number): string {
    return direction === 1 ? "+1" : direction === -1 ? "−1" : "0";
  }

  function statusVariant(status: string): "success" | "danger" | "warning" {
    return status === "approved" ? "success" : status === "rejected" ? "danger" : "warning";
  }

  function toggleLens(name: string, checked: boolean): void {
    selectedLenses = checked ? [...selectedLenses, name] : selectedLenses.filter((l) => l !== name);
  }

  function toggleToolState(name: string, checked: boolean): void {
    selectedTools = checked ? [...selectedTools, name] : selectedTools.filter((t) => t !== name);
  }

  let filtered = $derived(
    briefs.filter(
      (b) =>
        (statusFilter === "All" || b.status === statusFilter.toLowerCase()) &&
        (lensFilter === "All" || b.lens === lensFilter),
    ),
  );
</script>

<section class="panel research">
  <header class="panel-head">
    <h2>Research</h2>
    <Button variant="ghost" size="icon" class="size-7 text-muted-foreground hover:text-ink" onclick={loadAll} aria-label="Refresh research">
      <RotateCw class="size-3.5" />
    </Button>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <div class="run-bar">
    <h3>Run briefers</h3>
    <div class="lens-row">
      {#each lenses as l (l.name)}
        <label class="check">
          <Checkbox checked={selectedLenses.includes(l.name)} onCheckedChange={(c) => toggleLens(l.name, c)} disabled={running} />
          <span>{l.name}</span>
        </label>
      {/each}
    </div>
    <div class="tool-row">
      <span class="tool-label">Tools</span>
      {#each tools as t (t.name)}
        <label class="check">
          <Checkbox checked={selectedTools.includes(t.name)} onCheckedChange={(c) => toggleToolState(t.name, c)} disabled={running} />
          <span>{t.name}</span>
        </label>
      {/each}
    </div>
    <Textarea
      class="context mono min-h-11"
      placeholder="Optional context for this run…"
      bind:value={contextText}
      disabled={running}
    ></Textarea>
    <div class="run-row">
      <Button size="sm" onclick={run} disabled={running || selectedLenses.length === 0}>
        {running ? "Running…" : "Run"}
      </Button>
      <div class="chips">
        {#each runChips as chip (chip.lens)}
          <Badge variant={chip.ok ? "success" : "danger"}>{chip.lens}: {chip.ok ? "ok" : chip.error}</Badge>
        {/each}
      </div>
    </div>
  </div>

  <div class="cols">
    <div class="col list-col">
      <div class="filters">
        <select bind:value={statusFilter} aria-label="Status filter">
          {#each statuses as s}
            <option value={s}>{s}</option>
          {/each}
        </select>
        <select bind:value={lensFilter} aria-label="Lens filter">
          <option value="All">All lenses</option>
          {#each lenses as l (l.name)}
            <option value={l.name}>{l.name}</option>
          {/each}
        </select>
      </div>
      <ul>
        {#each filtered as b (b.brief_id)}
          <li class="brief-row">
            <button
              type="button"
              class={b.brief_id === selectedId ? "brief-btn sel" : "brief-btn"}
              onclick={() => select(b.brief_id)}
            >
              <Badge variant="outline">{b.lens}</Badge>
              <span class="num {dirBadgeClass(b.direction)}">{dirLabel(b.direction)}</span>
              <span class="conf mono">{(b.confidence * 100).toFixed(0)}%</span>
              <span class="thesis">{b.thesis}</span>
              <Badge variant={statusVariant(b.status)}>{b.status}{b.expired ? " · expired" : ""}</Badge>
            </button>
          </li>
        {/each}
        {#if filtered.length === 0}
          <li class="empty">No briefs.</li>
        {/if}
      </ul>
    </div>

    <div class="col detail-col">
      {#if selected}
        <ResearchBriefDetail brief={selected} busy={deciding} onDecide={onDecide} />
      {:else}
        <p class="empty">Select a brief to see details.</p>
      {/if}
    </div>
  </div>
</section>

<style>
  .research {
    display: flex;
    flex-direction: column;
    min-width: 320px;
    min-height: 0;
    flex: 1 1 0;
    border-radius: 6px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
  }
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
  }
  .panel-head h2 {
    margin: 0;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .run-bar {
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .run-bar h3 {
    margin: 0;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.07em;
    color: var(--faint);
    text-transform: uppercase;
  }
  .lens-row,
  .tool-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    font-size: 11px;
  }
  .tool-label {
    color: var(--faint);
    font-size: 10px;
    text-transform: uppercase;
  }
  .check {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--body);
    cursor: pointer;
  }
  .run-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .cols {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(220px, 2fr) minmax(280px, 3fr);
    overflow: hidden;
  }
  .col {
    overflow-y: auto;
    padding: 8px 10px;
  }
  .list-col {
    border-right: 1px solid var(--hairline);
  }
  .filters {
    display: flex;
    gap: 6px;
    margin-bottom: 6px;
  }
  .filters select {
    background: var(--surface-elevated);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    color: var(--body);
    font-size: 10px;
    padding: 2px 4px;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .brief-row {
    border-bottom: 1px solid var(--hairline);
  }
  .brief-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    width: 100%;
    padding: 4px 2px;
    font-size: 11px;
    cursor: pointer;
    background: none;
    border: none;
    text-align: left;
    min-height: 28px;
    color: inherit;
  }
  .brief-btn:hover {
    background: var(--row-hover);
  }
  .brief-btn.sel {
    background: color-mix(in srgb, var(--accent) 10%, transparent);
  }
  .dir-flat {
    color: var(--muted);
  }
  .conf {
    color: var(--faint);
    min-width: 34px;
    text-align: right;
  }
  .thesis {
    color: var(--body);
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .empty {
    color: var(--faint);
    border-bottom: none;
  }
  .error {
    color: var(--danger);
    font-size: 11px;
    padding: 8px 10px;
    margin: 0;
  }
</style>
