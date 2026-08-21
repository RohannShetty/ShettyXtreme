<script lang="ts">
  import { onMount } from "svelte";
  import type { KnowledgeDoc, RelatedDoc } from "../../lib/api";
  import { exportKnowledgeDoc, getRelatedDocs } from "../../lib/api";
  import { onMessage } from "../../lib/ws";
  import { Button } from "$lib/components/ui/button";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import { Download } from "@lucide/svelte";
  import { toast } from "svelte-sonner";
  import { evidenceItems, fmtTs, statusTagClass, strField } from "./knowledge-shared";

  let {
    selected = null,
    activating = false,
    onActivate = () => {},
    onRelatedSelect = (_id: string) => {},
  }: {
    selected?: KnowledgeDoc | null;
    activating?: boolean;
    onActivate?: () => void;
    onRelatedSelect?: (docId: string) => void;
  } = $props();

  let exporting: "md" | "pdf" | null = $state(null);
  let related: RelatedDoc[] = $state([]);
  let relatedLoading = $state(false);

  const STALE_MS = 60 * 60 * 1000;
  function isStale(ts: string | null): boolean {
    if (!ts) return false;
    const t = Date.parse(ts);
    return !Number.isNaN(t) && Date.now() - t > STALE_MS;
  }
  let isDocStale = $derived(selected ? isStale(selected.created_at) : false);
  let exportDisabled = $derived(exporting !== null || isDocStale);

  async function doExport(format: "md" | "pdf") {
    if (!selected || isDocStale) return;
    exporting = format;
    try {
      const blob = await exportKnowledgeDoc(selected.doc_id, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `doc-${selected.doc_id}.${format}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success(`Downloaded doc-${selected.doc_id}.${format}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    } finally {
      exporting = null;
    }
  }

  async function loadRelated(docId: string): Promise<void> {
    relatedLoading = true;
    try {
      const res = await getRelatedDocs(docId, 5);
      related = res.related ?? [];
    } catch {
      related = [];
    } finally {
      relatedLoading = false;
    }
  }

  // Fetch related docs when selection changes.
  let lastDocId: string | null = $state(null);
  $effect(() => {
    const id = selected?.doc_id ?? null;
    if (id && id !== lastDocId) {
      lastDocId = id;
      void loadRelated(id);
    } else if (!id) {
      lastDocId = null;
      related = [];
    }
  });

  onMount(() => {
    return onMessage("knowledge", (data) => {
      const ev = data as { event: string; data: unknown };
      if (ev.event !== "activated") return;
      // A newly activated doc may introduce edges / shared tags → refresh.
      if (selected?.doc_id) void loadRelated(selected.doc_id);
    });
  });
</script>

{#if selected}
  <h3 class="detail-title">{strField(selected.payload, "thesis") || selected.payload["title"]}</h3>
  {#if selected.kind}
    <p class="detail-meta mono">
      <span class={statusTagClass(selected.status)}>{selected.status}</span>
      <span>{selected.kind}</span>
      <span>{selected.source_ref}</span>
      {#if selected.activated_at}
        <span>activated {fmtTs(selected.activated_at)}</span>
      {/if}
    </p>
  {/if}
  {#if strField(selected.payload, "rationale")}
    <h4>Rationale</h4>
    <p class="detail-text">{strField(selected.payload, "rationale")}</p>
  {/if}
  {#if selected.tags.length > 0}
    <h4>Tags</h4>
    <div class="tags">
      {#each selected.tags as t (t.tag + t.kind)}
        <span class="tag">{t.kind}: {t.tag}</span>
      {/each}
    </div>
  {/if}
  {#if evidenceItems(selected.payload).length > 0}
    <h4>Evidence</h4>
    <ul class="evidence">
      {#each evidenceItems(selected.payload) as e, i (i)}
        <li>
          <span class="ev-item">{e.item}</span>
          {#if e.source}
            <span class="ev-source mono">{e.source}</span>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}
  <div class="detail-actions">
    <Button size="sm" class="self-start" onclick={onActivate} disabled={selected.status === "activated" || activating}>
      {selected.status === "activated" ? "Activated" : activating ? "Activating..." : "Activate"}
    </Button>
    {#if selected.status === "proposed" || selected.status === "activated"}
      <span title={isDocStale ? "Cannot export stale documents" : undefined}>
        <DropdownMenu.Root>
          <DropdownMenu.Trigger>
            {#snippet child({ props })}
              <Button {...props} variant="outline" size="sm" disabled={exportDisabled} aria-label={isDocStale ? "Export doc (disabled — stale document)" : "Export doc"}>
                <Download class="size-3.5" />
                {exporting ? `Exporting ${exporting.toUpperCase()}...` : "Export"}
              </Button>
            {/snippet}
          </DropdownMenu.Trigger>
          <DropdownMenu.Content align="start">
            <DropdownMenu.Item onSelect={() => doExport("md")} disabled={exportDisabled}>Export Markdown</DropdownMenu.Item>
            <DropdownMenu.Item onSelect={() => doExport("pdf")} disabled={exportDisabled}>Export PDF</DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Root>
      </span>
    {/if}
  </div>
  {#if related.length > 0 || relatedLoading}
    <div class="related-section" aria-label="Related documents">
      <h4>Related</h4>
      {#if relatedLoading}
        <p class="related-loading mono">Loading related…</p>
      {:else}
        <ul class="related-list">
          {#each related as r (r.doc_id)}
            <li>
              <button type="button" class="related-btn" onclick={() => onRelatedSelect(r.doc_id)} aria-label="Open related doc {r.title}">
                <span class="related-title">{r.title}</span>
                <span class="related-meta mono">{r.shared_tags.join(", ")} · score {r.score.toFixed(1)}</span>
              </button>
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
{:else}
  <p class="empty">Select a result to review it.</p>
{/if}

<style>
  .detail-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 10px;
  }
  .tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .tag {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    border: 1px solid var(--hairline-strong);
    border-radius: 4px;
    padding: 1px 5px;
    white-space: nowrap;
  }
  .tag.ok {
    color: var(--success);
    border-color: var(--success);
  }
  .tag.bad {
    color: var(--danger);
    border-color: var(--danger);
  }
  .tag.pending {
    color: var(--warning);
    border-color: var(--warning);
  }
  .empty {
    color: var(--faint);
    font-size: 11px;
    padding: 4px 0;
    border-bottom: none;
  }
  h3,
  h4 {
    margin: 0 0 6px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.07em;
    color: var(--faint);
    text-transform: uppercase;
  }
  .detail-title {
    text-transform: none !important;
    letter-spacing: 0 !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    color: var(--ink) !important;
  }
  .detail-meta {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin: 0 0 10px;
    color: var(--faint);
    font-size: 10px;
  }
  .detail-text {
    color: var(--body);
    font-size: 11px;
    line-height: 1.6;
    margin: 0 0 10px;
  }
  .evidence {
    margin: 0 0 10px;
    list-style: none;
    padding: 0;
  }
  .evidence li {
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding: 3px 0;
    font-size: 11px;
    border-bottom: 1px solid var(--hairline);
  }
  .ev-item {
    color: var(--body);
  }
  .ev-source {
    color: var(--faint);
    font-size: 9px;
  }
  .related-section {
    margin-top: 12px;
    padding-top: 8px;
    border-top: 1px solid var(--hairline);
  }
  .related-loading {
    color: var(--faint);
    font-size: 10px;
  }
  .related-list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .related-btn {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 2px;
    width: 100%;
    text-align: left;
    background: transparent;
    border: 1px solid var(--hairline);
    border-radius: 4px;
    padding: 6px 8px;
    cursor: pointer;
    transition: border-color 120ms, background-color 120ms;
  }
  .related-btn:hover {
    border-color: var(--hairline-strong);
    background: var(--row-hover);
  }
  .related-btn:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  .related-title {
    color: var(--ink);
    font-size: 11px;
    font-weight: 600;
    line-height: 14px;
  }
  .related-meta {
    color: var(--faint);
    font-size: 9px;
  }
</style>
