<script lang="ts">
  import type { KnowledgeDoc } from "../../lib/api";
  import { exportKnowledgeDoc } from "../../lib/api";
  import { Button } from "$lib/components/ui/button";
  import * as DropdownMenu from "$lib/components/ui/dropdown-menu";
  import { Download } from "@lucide/svelte";
  import { toast } from "svelte-sonner";
  import { evidenceItems, fmtTs, statusTagClass, strField } from "./knowledge-shared";

  let {
    selected = null,
    activating = false,
    onActivate = () => {},
  }: {
    selected?: KnowledgeDoc | null;
    activating?: boolean;
    onActivate?: () => void;
  } = $props();

  let exporting: "md" | "pdf" | null = $state(null);

  async function doExport(format: "md" | "pdf") {
    if (!selected) return;
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
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Export failed");
    } finally {
      exporting = null;
    }
  }
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
      <DropdownMenu.Root>
        <DropdownMenu.Trigger>
          {#snippet child({ props })}
            <Button {...props} variant="outline" size="sm" disabled={exporting !== null}>
              <Download class="size-3.5" />
              {exporting ? `Exporting ${exporting.toUpperCase()}...` : "Export"}
            </Button>
          {/snippet}
        </DropdownMenu.Trigger>
        <DropdownMenu.Content align="start">
          <DropdownMenu.Item onSelect={() => doExport("md")}>Export Markdown</DropdownMenu.Item>
          <DropdownMenu.Item onSelect={() => doExport("pdf")}>Export PDF</DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Root>
    {/if}
  </div>
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
</style>
