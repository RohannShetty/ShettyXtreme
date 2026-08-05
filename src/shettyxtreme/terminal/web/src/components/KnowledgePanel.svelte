<script lang="ts">
  import { onMount } from "svelte";
  import { get, post, postBody } from "../lib/api";
  import { onMessage } from "../lib/ws";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Textarea } from "$lib/components/ui/textarea";
  import { RefreshCw, RotateCw } from "@lucide/svelte";
  import KnowledgeDetail from "./knowledge/KnowledgeDetail.svelte";
  import { statusClass } from "./knowledge/knowledge-shared";
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
  let debounceTimer: number | undefined;
  let searchWrapEl: HTMLDivElement | undefined;
  let listEl: HTMLUListElement | undefined;
  let activeIndex = $state(-1);

  let selectedId = $derived(selected ? selected.doc_id : "");

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
    if (hits.length === 0) return;
    let idx = activeIndex;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      idx = idx < 0 ? 0 : (idx + 1) % hits.length;
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      idx = idx < 0 ? hits.length - 1 : (idx - 1 + hits.length) % hits.length;
    } else if (event.key === "Home") {
      event.preventDefault();
      idx = 0;
    } else if (event.key === "End") {
      event.preventDefault();
      idx = hits.length - 1;
    } else if (event.key === "Enter") {
      if (idx >= 0 && idx < hits.length) {
        event.preventDefault();
        void select(hits[idx].doc_id);
      }
      return;
    } else {
      return;
    }
    activeIndex = idx;
    const target = hits[idx];
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
</script>

<section class="panel knowledge">
  <header class="panel-head">
    <h2>Knowledge</h2>
    <div class="head-right">
      <span class="counts mono">{status.docs} docs · {status.proposed} prop · {status.activated} act · Last sync: {fmtLastSync(status.last_sync_at)}</span>
      <Button variant="ghost" size="icon" class="size-7 text-muted-foreground hover:text-ink" onclick={loadStatus} aria-label="Refresh knowledge status">
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
  <div class="note-box">
    <Input class="mono" type="text" placeholder="Note title…" bind:value={noteTitle} />
    <Textarea class="mono min-h-10" rows={2} placeholder="Note body — symbols/regimes auto-tagged…" bind:value={noteBody}></Textarea>
    <Button size="sm" class="self-start" onclick={saveNote} disabled={saving || !noteTitle.trim()}>
      {saving ? "Saving…" : "Save note"}
    </Button>
  </div>
  {#if syncResult}
    <p class="sync-result mono">{syncResult}</p>
  {/if}
  <div class="cols">
    <div class="col list-col">
      <ul class="hit-list" role="listbox" tabindex="0" aria-label="Knowledge search results" bind:this={listEl} onkeydown={onListKeydown}>
        {#each hits as h (h.doc_id)}
          {@const ts = hitCreatedAt(h)}
          <li>
            <button
              type="button"
              role="option"
              aria-selected={selectedId === h.doc_id}
              class:sel={selectedId === h.doc_id}
              class="hit-card"
              onclick={() => select(h.doc_id)}
            >
              <span class="hit-title">{h.title}</span>
              <span class="hit-snippet">{h.snippet}</span>
              <span class="hit-meta">
                <span class="chip {statusClass(h.status)}">{h.status}</span>
                <span class="src micro">{h.source_ref}</span>
                {#if ts}
                  <span class="time">{fmtHitTs(ts)}</span>
                {/if}
                {#if isStaleHit(h)}
                  <span class="stale">STALE</span>
                {/if}
              </span>
            </button>
          </li>
        {/each}
        {#if !searched && hits.length === 0}
          <li class="empty">Type a query to search knowledge.</li>
        {:else if searched && hits.length === 0}
          <li class="empty">No results.</li>
        {/if}
      </ul>
    </div>
    <div class="col detail-col">
      <KnowledgeDetail {selected} {activating} onActivate={() => activate()} />
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
  .panel-head h2 {
    margin: 0;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .head-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .counts {
    color: var(--faint);
    font-size: 9px;
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
  .note-box {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
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
    overflow-y: auto;
    padding: 8px 10px;
  }
  .list-col {
    border-right: 1px solid var(--hairline);
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
  /* Hit rows — surface-card cards, content in body face, timestamps in micro. */
  .hit-card {
    display: flex;
    flex-direction: column;
    gap: 3px;
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
  .hit-card:hover {
    background: var(--row-hover);
  }
  .hit-card.sel {
    background: var(--row-selected);
    box-shadow: inset 2px 0 0 var(--accent);
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
  .chip.ok {
    color: var(--success);
    border-color: var(--success);
  }
  .chip.pending {
    color: var(--warning);
    border-color: var(--warning);
  }
  .chip.bad {
    color: var(--danger);
    border-color: var(--danger);
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
