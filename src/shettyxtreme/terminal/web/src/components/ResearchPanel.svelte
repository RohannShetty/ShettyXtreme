<script lang="ts">
  import { onMount } from "svelte";
  import { get, post, postBody } from "../lib/api";
  import { onMessage } from "../lib/ws";
  import ResearchBriefDetail from "./ResearchBriefDetail.svelte";
  import { Button } from "$lib/components/ui/button";
  import { Badge } from "$lib/components/ui/badge";
  import { Textarea } from "$lib/components/ui/textarea";
  import { Select, SelectContent, SelectItem, SelectTrigger } from "$lib/components/ui/select";
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
  let listEl: HTMLUListElement | undefined;
  let activeIndex = $state(-1);

  const statuses = ["All", "Proposed", "Approved", "Rejected"];

  // Staleness marker (DESIGN.md §4): a brief whose generation time is older
  // than one hour is flagged STALE in the row corner.
  const STALE_MS = 60 * 60 * 1000;

  function isStale(asOf: string): boolean {
    const t = Date.parse(asOf);
    return !Number.isNaN(t) && Date.now() - t > STALE_MS;
  }

  function fmtTime(asOf: string): string {
    const d = new Date(asOf);
    return Number.isNaN(d.getTime()) ? "—" : d.toLocaleTimeString("en-IN", { hour12: false });
  }

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

  // Keyboard list navigation: arrows move the highlight, Enter opens the
  // highlighted brief in the detail pane, Home/End jump to the ends.
  function onListKeydown(event: KeyboardEvent): void {
    if (filtered.length === 0) return;
    let idx = activeIndex;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      idx = idx < 0 ? 0 : (idx + 1) % filtered.length;
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      idx = idx < 0 ? filtered.length - 1 : (idx - 1 + filtered.length) % filtered.length;
    } else if (event.key === "Home") {
      event.preventDefault();
      idx = 0;
    } else if (event.key === "End") {
      event.preventDefault();
      idx = filtered.length - 1;
    } else if (event.key === "Enter") {
      if (idx >= 0 && idx < filtered.length) {
        event.preventDefault();
        select(filtered[idx].brief_id);
      }
      return;
    } else {
      return;
    }
    activeIndex = idx;
    const target = filtered[idx];
    if (target) {
      select(target.brief_id);
      listEl?.querySelector(".sel")?.scrollIntoView({ block: "nearest" });
    }
  }
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
        <label class="check" class:disabled={running}>
          <button
            type="button"
            role="switch"
            aria-checked={selectedLenses.includes(l.name)}
            aria-label={`Enable ${l.name} lens`}
            class:on={selectedLenses.includes(l.name)}
            class="switch"
            disabled={running}
            onclick={() => toggleLens(l.name, !selectedLenses.includes(l.name))}
          >
            <span class="knob"></span>
          </button>
          <span>{l.name}</span>
        </label>
      {/each}
    </div>
    <div class="tool-row">
      <span class="tool-label">Tools</span>
      {#each tools as t (t.name)}
        <label class="check" class:disabled={running}>
          <button
            type="button"
            role="switch"
            aria-checked={selectedTools.includes(t.name)}
            aria-label={`Enable ${t.name} tool`}
            class:on={selectedTools.includes(t.name)}
            class="switch"
            disabled={running}
            onclick={() => toggleToolState(t.name, !selectedTools.includes(t.name))}
          >
            <span class="knob"></span>
          </button>
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
        <Select type="single" value={statusFilter} onValueChange={(v) => (statusFilter = v)}>
          <SelectTrigger class="h-7 w-[110px] text-[11px]" aria-label="Status filter">
            <span>{statusFilter}</span>
          </SelectTrigger>
          <SelectContent>
            {#each statuses as s (s)}
              <SelectItem value={s} label={s}>{s}</SelectItem>
            {/each}
          </SelectContent>
        </Select>
        <Select type="single" value={lensFilter} onValueChange={(v) => (lensFilter = v)}>
          <SelectTrigger class="h-7 w-[130px] text-[11px]" aria-label="Lens filter">
            <span>{lensFilter === "All" ? "All lenses" : lensFilter}</span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="All" label="All">All lenses</SelectItem>
            {#each lenses as l (l.name)}
              <SelectItem value={l.name} label={l.name}>{l.name}</SelectItem>
            {/each}
          </SelectContent>
        </Select>
      </div>
      <ul class="brief-list" role="listbox" tabindex="0" aria-label="Research briefs" bind:this={listEl} onkeydown={onListKeydown}>
        {#each filtered as b (b.brief_id)}
          <li>
            <button
              type="button"
              role="option"
              aria-selected={b.brief_id === selectedId}
              class:sel={b.brief_id === selectedId}
              class="brief-card"
              onclick={() => select(b.brief_id)}
            >
              <span class="thesis ticker">{b.thesis}</span>
              <span class="meta">
                <span class="caption">{b.lens}</span>
                <span class="dir num {dirBadgeClass(b.direction)}">{dirLabel(b.direction)}</span>
                <span class="conf num">{(b.confidence * 100).toFixed(0)}%</span>
                {#if isStale(b.as_of)}
                  <span class="stale">STALE</span>
                {/if}
                <span class="time num">{fmtTime(b.as_of)}</span>
                <Badge variant={statusVariant(b.status)}>{b.status}{b.expired ? " · expired" : ""}</Badge>
              </span>
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
    min-width: 0;
    min-height: 0;
    flex: 1 1 0;
    border-radius: 6px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    /* Container-query breakpoint for the dock: stack list over detail when
       narrow (DESIGN.md §8 — breakpoints follow container queries). */
    container-type: inline-size;
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
  /* Toggle / switch — DESIGN.md §4: off = hairline-strong track + muted knob,
     on = accent track + white knob. 26×14px, 120ms color/position transition. */
  .check {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    color: var(--body);
    cursor: pointer;
  }
  .check.disabled {
    cursor: default;
    opacity: 0.5;
  }
  .switch {
    position: relative;
    display: inline-flex;
    align-items: center;
    width: 26px;
    height: 14px;
    padding: 0;
    border: 1px solid var(--hairline-strong);
    border-radius: 7px;
    background: var(--hairline-strong);
    cursor: pointer;
    flex: none;
    transition: background-color 120ms ease-out, border-color 120ms ease-out;
  }
  .switch .knob {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    background: var(--muted);
    transform: translateX(1px);
    transition: transform 120ms ease-out, background-color 120ms ease-out;
  }
  .switch.on {
    background: var(--accent);
    border-color: var(--accent);
  }
  .switch.on .knob {
    background: #fff;
    transform: translateX(13px);
  }
  .switch:disabled {
    cursor: default;
  }
  .switch:focus-visible {
    outline: none;
    box-shadow: 0 0 0 2px var(--canvas), 0 0 0 4px var(--focus-ring);
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
    grid-template-columns: minmax(0, 2fr) minmax(0, 3fr);
    overflow: hidden;
  }
  @container (max-width: 460px) {
    .cols {
      grid-template-columns: 1fr;
      grid-template-rows: minmax(96px, 2fr) minmax(120px, 3fr);
    }
    .list-col {
      border-right: none;
      border-bottom: 1px solid var(--hairline);
    }
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
    margin-bottom: 8px;
  }
  ul.brief-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  ul.brief-list:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  /* Brief rows — surface-card cards, thesis in ticker face, meta in caption. */
  .brief-card {
    display: flex;
    flex-direction: column;
    gap: 4px;
    width: 100%;
    padding: 6px 8px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    color: inherit;
    text-align: left;
    cursor: pointer;
    transition: background-color 120ms ease-out, border-color 120ms ease-out;
  }
  .brief-card:hover {
    background: var(--row-hover);
  }
  .brief-card.sel {
    background: var(--row-selected);
    box-shadow: inset 2px 0 0 var(--accent);
  }
  .thesis {
    color: var(--ink);
    font-family: var(--font-mono);
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.02em;
    line-height: 16px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .meta .caption {
    color: var(--muted);
    font-size: 11px;
  }
  .dir {
    font-size: 11px;
    font-weight: 600;
  }
  .conf {
    color: var(--faint);
    font-size: 11px;
  }
  .time {
    color: var(--faint);
    font-size: 10px;
  }
  .dir-flat {
    color: var(--muted);
  }
  /* Staleness marker — DESIGN.md §4: warning micro "STALE" chip. */
  .stale {
    font-family: var(--font-mono);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--warning);
    border: 1px solid var(--warning);
    border-radius: 2px;
    padding: 0 4px;
    line-height: 14px;
    white-space: nowrap;
  }
  .empty {
    color: var(--faint);
    font-size: 11px;
    padding: 4px 0;
  }
  .error {
    color: var(--danger);
    font-size: 11px;
    padding: 8px 10px;
    margin: 0;
  }
</style>
