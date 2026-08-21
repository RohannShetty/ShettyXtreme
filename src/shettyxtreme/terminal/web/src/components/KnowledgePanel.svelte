<script lang="ts">
  import { onMount } from "svelte";
  import { get, post, postBody } from "../lib/api";
  import { onMessage } from "../lib/ws";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Badge } from "$lib/components/ui/badge";
  import { Card } from "$lib/components/ui/card";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import { Skeleton } from "$lib/components/ui/skeleton";
  import { Tabs, TabsList, TabsTrigger } from "$lib/components/ui/tabs";
  import { Textarea } from "$lib/components/ui/textarea";
  import { RefreshCw, RotateCw } from "@lucide/svelte";
  import KnowledgeDetail from "./knowledge/KnowledgeDetail.svelte";
  import KnowledgeGraph from "./knowledge/KnowledgeGraph.svelte";
  import type {
    KnowledgeDoc,
    KnowledgeNoteRequest,
    KnowledgeSearchHit,
    KnowledgeSearchResponse,
    KnowledgeStatusResponse,
    KnowledgeSyncResponse,
  } from "../lib/api";

  let query = $state("");
  let hits: KnowledgeSearchHit[] = $state([]);
  let selected = $state<KnowledgeDoc | null>(null);
  let docs: KnowledgeDoc[] = $state([]);
  let status = $state<KnowledgeStatusResponse>({
    docs: 0,
    proposed: 0,
    activated: 0,
    tags: 0,
    last_sync_at: null,
    last_sync_result: null,
  });
  let error = $state("");
  let searched = $state(false);
  let searching = $state(false);
  let syncing = $state(false);
  let activating = $state(false);
  let syncResult = $state("");
  let noteTitle = $state("");
  let noteBody = $state("");
  let saving = $state(false);
  let kindFilter = $state("All");
  let debounceTimer: number | undefined;
  let searchWrapEl = $state<HTMLDivElement | undefined>(undefined);
  let listEl = $state<HTMLUListElement | undefined>(undefined);
  let activeIndex = $state(-1);

  let selectedId = $derived(selected ? selected.doc_id : "");

  const kinds = [
    { value: "All", label: "All" },
    { value: "strategy", label: "Strategies" },
    { value: "pattern", label: "Patterns" },
    { value: "note", label: "Notes" },
    { value: "Graph", label: "Graph" },
  ];

  // doc_id → full doc, so hit rows can show created_at timestamps and the
  // STALE marker without a second API call (docs load once, then cache).
  let docIndex = $derived(new Map(docs.map((d) => [d.doc_id, d])));

  // Staleness marker (DESIGN.md §4): knowledge older than one hour is STALE.
  const STALE_MS = 60 * 60 * 1000;

  function hitCreatedAt(h: KnowledgeSearchHit): string | null {
    return docIndex.get(h.doc_id)?.created_at ?? null;
  }

  function isStaleHit(h: KnowledgeSearchHit): boolean {
    const ts = hitCreatedAt(h);
    if (!ts) return false;
    const t = Date.parse(ts);
    return !Number.isNaN(t) && Date.now() - t > STALE_MS;
  }

  function fmtHitTs(ts: string): string {
    return ts.slice(0, 16).replace("T", " ");
  }

  // "Last sync" indicator — local HH:MM, or "Never" when nothing synced yet.
  function fmtLastSync(ts: string | null): string {
    if (!ts) return "Never";
    const t = Date.parse(ts);
    if (Number.isNaN(t)) return "Never";
    const d = new Date(t);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    return `${hh}:${mm}`;
  }

  // Non-success sync outcomes are surfaced next to the time so a stale or
  // failed sync is never mistaken for a healthy one (roadmap #9).
  let lastSyncSuffix = $derived(
    status.last_sync_result && status.last_sync_result !== "success"
      ? ` (${status.last_sync_result})`
      : "",
  );

  function markActivated(docId: string, doc: KnowledgeDoc): void {
    hits = hits.map((h) => (h.doc_id === docId ? { ...h, status: "activated" } : h));
    docs = docs.map((d) => (d.doc_id === docId ? doc : d));
    if (selected && selected.doc_id === docId) selected = doc;
  }

  onMount(() => {
    loadStatus();
    const off = onMessage("knowledge", (data) => {
      const ev = data as { event: string; data: unknown };
      if (ev.event !== "activated") return;
      const doc = ev.data as KnowledgeDoc;
      if (doc && typeof doc.doc_id === "string") markActivated(doc.doc_id, doc);
    });
    window.addEventListener("keydown", onGlobalKeydown);
    return () => {
      off();
      window.removeEventListener("keydown", onGlobalKeydown);
    };
  });

  // Ctrl+F focuses the search box (workstation shortcut) — but never hijacks
  // focus when the operator is already typing in an input/textarea.
  function onGlobalKeydown(event: KeyboardEvent): void {
    if (!event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key.toLowerCase() !== "f") return;
    const t = event.target as HTMLElement | null;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
    event.preventDefault();
    const el = searchWrapEl?.querySelector<HTMLInputElement>("input");
    el?.focus();
    el?.select();
  }

  async function loadStatus(): Promise<void> {
    try {
      status = await get<KnowledgeStatusResponse>("/api/knowledge/status");
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function search(): Promise<void> {
    if (searching) return;
    searching = true;
    searched = true;
    error = "";
    activeIndex = -1;
    try {
      const resp = await get<KnowledgeSearchResponse>(
        `/api/knowledge/search?q=${encodeURIComponent(query)}&limit=20`,
      );
      hits = resp.hits;
      selected = null;
      if (hits.length > 0 && docs.length === 0) {
        try {
          const list = await get<{ docs: KnowledgeDoc[] }>("/api/knowledge/docs");
          docs = list.docs;
        } catch {
          /* detail falls back to hit fields */
        }
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
      hits = [];
    } finally {
      searching = false;
    }
  }

  function onInput(): void {
    if (debounceTimer !== undefined) window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => {
      search();
    }, 300);
  }

  function onKeydown(event: KeyboardEvent): void {
    if (event.key === "Enter") {
      if (debounceTimer !== undefined) window.clearTimeout(debounceTimer);
      search();
    }
  }

  async function select(docId: string): Promise<void> {
    const hit = hits.find((h) => h.doc_id === docId);
    if (docs.length === 0) {
      try {
        const list = await get<{ docs: KnowledgeDoc[] }>("/api/knowledge/docs");
        docs = list.docs;
      } catch {
        /* fall back to hit-only detail */
      }
    }
    const doc = docs.find((d) => d.doc_id === docId);
    if (doc) {
      selected = doc;
    } else if (hit) {
      selected = {
        doc_id: hit.doc_id,
        kind: hit.kind,
        source_ref: hit.source_ref,
        payload: { thesis: hit.title },
        status: hit.status,
        created_at: null,
        activated_at: null,
        tags: hit.tags,
      };
    }
  }

  // Arrow keys navigate the hit list; Enter opens the highlighted hit.
  function onListKeydown(event: KeyboardEvent): void {
    if (filteredHits.length === 0) return;
    let idx = activeIndex;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      idx = idx < 0 ? 0 : (idx + 1) % filteredHits.length;
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      idx = idx < 0 ? filteredHits.length - 1 : (idx - 1 + filteredHits.length) % filteredHits.length;
    } else if (event.key === "Home") {
      event.preventDefault();
      idx = 0;
    } else if (event.key === "End") {
      event.preventDefault();
      idx = filteredHits.length - 1;
    } else if (event.key === "Enter") {
      if (idx >= 0 && idx < filteredHits.length) {
        event.preventDefault();
        void select(filteredHits[idx].doc_id);
      }
      return;
    } else {
      return;
    }
    activeIndex = idx;
    const target = filteredHits[idx];
    if (target) {
      void select(target.doc_id);
      listEl?.querySelector(".sel")?.scrollIntoView({ block: "nearest" });
    }
  }

  async function activate(): Promise<void> {
    if (!selected || activating || selected.status === "activated") return;
    activating = true;
    error = "";
    try {
      const doc = await post<KnowledgeDoc>(`/api/knowledge/docs/${selected.doc_id}/activate`);
      markActivated(doc.doc_id, doc);
      await loadStatus();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      activating = false;
    }
  }

  async function sync(): Promise<void> {
    if (syncing) return;
    syncing = true;
    syncResult = "";
    error = "";
    try {
      const resp = await post<KnowledgeSyncResponse>("/api/knowledge/sync");
      syncResult = `ingested ${resp.ingested} · undecided ${resp.skipped_undecided} · dupes ${resp.skipped_duplicate}`;
      await loadStatus();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      syncing = false;
    }
  }

  async function saveNote(): Promise<void> {
    if (saving || !noteTitle.trim()) return;
    saving = true;
    error = "";
    try {
      await postBody<KnowledgeDoc>("/api/knowledge/notes", {
        title: noteTitle.trim(),
        body: noteBody,
      } satisfies KnowledgeNoteRequest);
      noteTitle = "";
      noteBody = "";
      await loadStatus();
      await search();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      saving = false;
    }
  }

  function statusVariant(statusVal: string): "success" | "warning" | "danger" {
    return statusVal === "activated" ? "success" : statusVal === "proposed" ? "warning" : "danger";
  }

  let filteredHits = $derived(
    kindFilter === "All" || kindFilter === "Graph" ? hits : hits.filter((h) => h.kind === kindFilter),
  );

  let graphKind = $derived(kindFilter === "All" || kindFilter === "Graph" ? undefined : kindFilter);

  function onGraphNodeClick(event: Event): void {
    const ce = event as CustomEvent<{ tag: string; kind: string; count: number }>;
    const tag = ce.detail?.tag;
    if (!tag) return;
    query = tag;
    kindFilter = "All";
    void search();
  }
</script>

<section class="panel knowledge">
  <header class="panel-head">
    <div class="titles">
      <span class="eyebrow">Library</span>
      <h2>Knowledge</h2>
    </div>
    <div class="head-right">
      <span class="counts mono">
        {status.docs} docs · {status.proposed} prop · {status.activated} act · Last sync: {fmtLastSync(status.last_sync_at)}{lastSyncSuffix}
      </span>
      <Button
        variant="ghost"
        size="icon"
        class="size-7 text-muted-foreground hover:text-ink"
        onclick={loadStatus}
        aria-label="Refresh knowledge status"
      >
        <RotateCw class="size-3.5" />
      </Button>
    </div>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <div class="controls">
    <div class="search-wrap" bind:this={searchWrapEl}>
      <Input
        class="mono"
        type="text"
        placeholder="Search knowledge… (Ctrl+F)"
        bind:value={query}
        oninput={onInput}
        onkeydown={onKeydown}
        aria-label="Search knowledge"
      />
    </div>
    <Button size="sm" onclick={search} disabled={searching}>{searching ? "Searching…" : "Search"}</Button>
    <Button size="sm" variant="secondary" onclick={sync} disabled={syncing}>
      {#if syncing}
        <RefreshCw class="size-3.5 animate-spin" />
      {:else}
        <RefreshCw class="size-3.5" />
      {/if}
      {syncing ? "Syncing…" : "Sync"}
    </Button>
  </div>

  <Card class="knowledge-note-card">
    <div class="knowledge-note-inner">
      <div class="knowledge-note-header">Add note</div>
      <Input class="mono" type="text" placeholder="Note title…" bind:value={noteTitle} />
      <Textarea class="mono min-h-10" rows={2} placeholder="Note body — symbols/regimes auto-tagged…" bind:value={noteBody}></Textarea>
      <Button size="sm" class="self-start" onclick={saveNote} disabled={saving || !noteTitle.trim()}>
        {saving ? "Saving…" : "Save note"}
      </Button>
    </div>
  </Card>

  {#if syncResult}
    <p class="sync-result mono">{syncResult}</p>
  {/if}

  <div class="cols">
    <div class="col list-col">
      <Tabs value={kindFilter} onValueChange={(v) => (kindFilter = v)} class="filter-tabs">
        <TabsList class="w-full">
          {#each kinds as k (k.value)}
            <TabsTrigger value={k.value}>{k.label}</TabsTrigger>
          {/each}
        </TabsList>
      </Tabs>

      {#if kindFilter === "Graph"}
        <div class="graph-wrap" role="region" aria-label="Knowledge graph">
          <!-- svelte-ignore event_directive_deprecated -->
          <KnowledgeGraph kind={graphKind} limit={100} on:graph-node-click={onGraphNodeClick} />
        </div>
      {:else}
        <ScrollArea class="h-full">
        {#if searching}
          <ul class="hit-list" aria-label="Knowledge search results loading">
            {#each { length: 4 } as _, i (i)}
              <li>
                <Card class="knowledge-hit-card">
                  <div class="hit-inner">
                    <Skeleton class="h-4 w-3/4" />
                    <Skeleton class="h-8 w-full" />
                    <div class="flex gap-2 pt-1">
                      <Skeleton class="h-4 w-16" />
                      <Skeleton class="h-4 w-12" />
                    </div>
                  </div>
                </Card>
              </li>
            {/each}
          </ul>
        {:else}
          <ul
            class="hit-list"
            role="listbox"
            tabindex="0"
            aria-label="Knowledge search results"
            bind:this={listEl}
            onkeydown={onListKeydown}
          >
            {#each filteredHits as h (h.doc_id)}
              {@const ts = hitCreatedAt(h)}
              <li>
                <Card class={["knowledge-hit-card", selectedId === h.doc_id ? "selected" : ""].join(" ")}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={selectedId === h.doc_id}
                    class:sel={selectedId === h.doc_id}
                    class="hit-btn"
                    onclick={() => select(h.doc_id)}
                  >
                    <div class="hit-inner">
                      <span class="hit-title">{h.title}</span>
                      <span class="hit-snippet">{h.snippet}</span>
                      <div class="hit-meta">
                        <Badge variant={statusVariant(h.status)}>{h.status}</Badge>
                        <span class="kind chip">{h.kind}</span>
                        <span class="src micro">{h.source_ref}</span>
                        {#if ts}
                          <span class="time">{fmtHitTs(ts)}</span>
                        {/if}
                        {#if isStaleHit(h)}
                          <Badge class="border-warning text-warning">STALE</Badge>
                        {/if}
                      </div>
                    </div>
                  </button>
                </Card>
              </li>
            {/each}
            {#if !searched && hits.length === 0}
              <li class="empty">Type a query to search knowledge.</li>
            {:else if searched && hits.length === 0}
              <li class="empty">No results.</li>
            {:else if filteredHits.length === 0 && hits.length > 0}
              <li class="empty">No {kindFilter === "All" ? "" : kindFilter} results.</li>
            {/if}
          </ul>
        {/if}
      </ScrollArea>
      {/if}
    </div>

    <div class="col detail-col">
      <ScrollArea class="h-full">
        <KnowledgeDetail {selected} {activating} onActivate={() => activate()} />
      </ScrollArea>
    </div>
  </div>
</section>

<style>
  .knowledge {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    flex: 1 1 0;
    border-radius: 6px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    /* Container-query breakpoint for the dock: stack hits over detail when
       narrow (DESIGN.md §8). */
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
  .head-right {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .counts {
    color: var(--faint);
    font-size: 9px;
    white-space: nowrap;
  }
  .controls {
    display: flex;
    gap: 6px;
    padding: 8px 10px;
    align-items: center;
  }
  .search-wrap {
    flex: 1;
    min-width: 0;
  }
  .search-wrap :global(input) {
    width: 100%;
  }
  :global(.knowledge-note-card) {
    margin: 0 10px 8px;
    border: 1px solid var(--hairline);
    background: var(--surface-card);
  }
  .knowledge-note-inner {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 6px 10px 8px;
  }
  .knowledge-note-header {
    padding: 8px 10px 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.07em;
    text-transform: uppercase;
    color: var(--faint);
  }
  .sync-result {
    margin: 0 10px 6px;
    font-size: 10px;
    color: var(--muted);
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
  ul.hit-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  ul.hit-list:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  /* Hit card — shadcn Card with custom compact content. */
  :global(.knowledge-hit-card) {
    border-color: var(--hairline);
    background: var(--surface-card);
    transition: background-color 120ms ease-out, border-color 120ms ease-out;
  }
  :global(.knowledge-hit-card):hover {
    border-color: var(--hairline-strong);
    background: var(--row-hover);
  }
  :global(.knowledge-hit-card.selected) {
    background: var(--row-selected);
    border-color: var(--accent);
    box-shadow: inset 2px 0 0 var(--accent);
  }
  .hit-btn {
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
  .hit-btn:focus-visible {
    outline: none;
  }
  .hit-inner {
    display: flex;
    flex-direction: column;
    gap: 3px;
    padding: 6px 8px;
  }
  .hit-title {
    color: var(--ink);
    font-weight: 600;
    font-size: 12px;
    line-height: 16px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .hit-snippet {
    color: var(--body);
    font-size: 11px;
    line-height: 1.45;
    overflow: hidden;
    display: -webkit-box;
    line-clamp: 2;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  .hit-meta {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 6px;
  }
  .hit-meta .micro {
    font-size: 10px;
  }
  .chip {
    font-family: var(--font-mono);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
    border: 1px solid var(--hairline-strong);
    border-radius: 2px;
    padding: 0 4px;
    line-height: 14px;
    white-space: nowrap;
  }
  .src {
    color: var(--faint);
  }
  .time {
    color: var(--faint);
    font-family: var(--font-mono);
    font-size: 10px;
    font-variant-numeric: tabular-nums;
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
