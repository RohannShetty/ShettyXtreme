<script lang="ts">
  import { onMount } from "svelte";
  import { get, post, postBody } from "../lib/api";
  import { onMessage } from "../lib/ws";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Textarea } from "$lib/components/ui/textarea";
  import { RefreshCw, RotateCw } from "@lucide/svelte";
  import KnowledgeDetail from "./knowledge/KnowledgeDetail.svelte";
  import KnowledgeHitList from "./knowledge/KnowledgeHitList.svelte";
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
  let status = $state({ docs: 0, proposed: 0, activated: 0, tags: 0 });
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

  let selectedId = $derived(selected ? selected.doc_id : "");

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
    return off;
  });

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
    try {
      const resp = await get<KnowledgeSearchResponse>(
        `/api/knowledge/search?q=${encodeURIComponent(query)}&limit=20`,
      );
      hits = resp.hits;
      selected = null;
      if (docs.length === 0 && hits.length > 0) {
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
      <span class="counts mono">{status.docs} docs · {status.proposed} prop · {status.activated} act</span>
      <Button variant="ghost" size="icon" class="size-7 text-muted-foreground hover:text-ink" onclick={loadStatus} aria-label="Refresh knowledge status">
        <RotateCw class="size-3.5" />
      </Button>
    </div>
  </header>
  {#if error}
    <p class="error">{error}</p>
  {/if}
  <div class="controls">
    <Input class="mono h-7" type="text" placeholder="Search knowledge…" bind:value={query} oninput={onInput} onkeydown={onKeydown} />
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
    <Input class="mono h-7" type="text" placeholder="Note title…" bind:value={noteTitle} />
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
      <KnowledgeHitList {hits} {searched} selectedId={selectedId} onSelect={(id) => select(id)} />
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
  .error {
    color: var(--danger);
    font-size: 11px;
    padding: 8px 10px;
    margin: 0;
  }
</style>
