<script lang="ts">
  import { onMount } from "svelte";
  import { get, post, postBody } from "../lib/api";
  import { onMessage } from "../lib/ws";
  import ResearchBriefDetail from "./ResearchBriefDetail.svelte";
  import { Button } from "$lib/components/ui/button";
  import { Badge } from "$lib/components/ui/badge";
  import { Card } from "$lib/components/ui/card";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import { Skeleton } from "$lib/components/ui/skeleton";
  import { Tabs, TabsList, TabsTrigger } from "$lib/components/ui/tabs";
  import { Textarea } from "$lib/components/ui/textarea";
  import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
  } from "$lib/components/ui/select";
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
  let loading = $state(false);
  let listEl = $state<HTMLUListElement | undefined>(undefined);
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
    loading = true;
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
    } finally {
      loading = false;
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
    <div class="titles">
      <span class="eyebrow">Intelligence</span>
      <h2>Research</h2>
    </div>
    <Button
      variant="ghost"
      size="icon"
      class="size-7 text-muted-foreground hover:text-ink"
      onclick={loadAll}
      aria-label="Refresh research"
    >
      <RotateCw class="size-3.5" />
    </Button>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <Card class="research-run-card">
    <div class="research-run-inner">
      <div class="research-run-header">Run briefers</div>
      <div class="toggle-group">
        <div class="toggle-row">
          <span class="row-label">Lenses</span>
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
        <div class="toggle-row">
          <span class="row-label">Tools</span>
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
      </div>
      <Textarea
        class="context mono min-h-10"
        placeholder="Optional context for this run…"
        bind:value={contextText}
        disabled={running}
      ></Textarea>
      <div class="run-actions">
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
  </Card>

  <div class="cols">
    <div class="col list-col">
      <Tabs value={statusFilter} onValueChange={(v) => (statusFilter = v)} class="filter-tabs">
        <TabsList class="w-full">
          {#each statuses as s (s)}
            <TabsTrigger value={s}>{s}</TabsTrigger>
          {/each}
        </TabsList>
      </Tabs>

      <div class="list-tools">
        <Select type="single" value={lensFilter} onValueChange={(v) => (lensFilter = v)}>
          <SelectTrigger class="h-7 w-full text-[11px]" aria-label="Lens filter">
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

      <ScrollArea class="h-full">
        {#if loading}
          <ul class="brief-list" aria-label="Research briefs loading">
            {#each { length: 4 } as _, i (i)}
              <li>
                <Card class="research-brief-card">
                  <div class="brief-inner">
                    <Skeleton class="h-4 w-3/4" />
                    <div class="flex gap-2 pt-2">
                      <Skeleton class="h-4 w-16" />
                      <Skeleton class="h-4 w-10" />
                      <Skeleton class="h-4 w-12" />
                    </div>
                  </div>
                </Card>
              </li>
            {/each}
          </ul>
        {:else}
          <ul
            class="brief-list"
            role="listbox"
            tabindex="0"
            aria-label="Research briefs"
            bind:this={listEl}
            onkeydown={onListKeydown}
          >
            {#each filtered as b (b.brief_id)}
              <li>
                <Card class={["research-brief-card", b.brief_id === selectedId ? "selected" : ""].join(" ")}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={b.brief_id === selectedId}
                    class:sel={b.brief_id === selectedId}
                    class="brief-btn"
                    onclick={() => select(b.brief_id)}
                  >
                    <div class="brief-inner">
                      <div class="brief-top">
                        <span class="thesis">{b.thesis}</span>
                        <Badge variant={statusVariant(b.status)}>
                          {b.status}{b.expired ? " · expired" : ""}
                        </Badge>
                      </div>
                      <div class="meta">
                        <Badge variant="outline">{b.lens}</Badge>
                        <span class="dir num {dirBadgeClass(b.direction)}">{dirLabel(b.direction)}</span>
                        <span class="conf num">{(b.confidence * 100).toFixed(0)}%</span>
                        {#if isStale(b.as_of)}
                          <Badge class="border-warning text-warning">STALE</Badge>
                        {/if}
                        <span class="time num">{fmtTime(b.as_of)}</span>
                      </div>
                    </div>
                  </button>
                </Card>
              </li>
            {/each}
            {#if filtered.length === 0}
              <li class="empty">No briefs.</li>
            {/if}
          </ul>
        {/if}
      </ScrollArea>
    </div>

    <div class="col detail-col">
      <ScrollArea class="h-full">
        {#if selected}
          <ResearchBriefDetail brief={selected} busy={deciding} onDecide={onDecide} />
        {:else}
          <p class="empty">Select a brief to see details.</p>
        {/if}
      </ScrollArea>
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
  .titles {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .eyebrow {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--faint);
  }
  .panel-head h2 {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
  }
  :global(.research-run-card) {
    margin: 8px 10px 0;
    border: 1px solid var(--hairline);
    background: var(--surface-card);
  }
  .research-run-inner {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 6px 10px 8px;
  }
  .research-run-header {
    padding: 8px 10px 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--faint);
  }
  .toggle-group {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .toggle-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    font-size: 11px;
  }
  .row-label {
    color: var(--faint);
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.06em;
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
  .context {
    font-size: 12px;
    line-height: 1.5;
  }
  .run-actions {
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
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  .list-col {
    border-right: 1px solid var(--hairline);
    padding: 8px 10px;
    gap: 6px;
  }
  .detail-col {
    padding: 8px 10px;
  }
  .list-tools {
    display: flex;
    gap: 6px;
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
  /* Brief card — shadcn Card with custom compact content. */
  :global(.research-brief-card) {
    border-color: var(--hairline);
    background: var(--surface-card);
    transition: background-color 120ms ease-out, border-color 120ms ease-out;
  }
  :global(.research-brief-card):hover {
    border-color: var(--hairline-strong);
    background: var(--row-hover);
  }
  :global(.research-brief-card.selected) {
    background: var(--row-selected);
    border-color: var(--accent);
    box-shadow: inset 2px 0 0 var(--accent);
  }
  .brief-btn {
    display: block;
    width: 100%;
    margin: 0;
    padding: 0;
    border: none;
    background: transparent;
    color: inherit;
    text-align: left;
    cursor: pointer;
  }
  .brief-btn:focus-visible {
    outline: none;
  }
  .brief-inner {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 6px 8px;
  }
  .brief-top {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 8px;
    min-width: 0;
  }
  .thesis {
    color: var(--ink);
    font-size: 12px;
    font-weight: 600;
    line-height: 16px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }
  .meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
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
