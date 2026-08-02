<script lang="ts">
  import type { KnowledgeSearchHit } from "../../lib/api";
  import { statusTagClass } from "./knowledge-shared";

  let {
    hits = [],
    selectedId = "",
    searched = false,
    onSelect = (_docId: string) => {},
  }: {
    hits?: KnowledgeSearchHit[];
    selectedId?: string;
    searched?: boolean;
    onSelect?: (docId: string) => void;
  } = $props();
</script>

<ul>
  {#each hits as h (h.doc_id)}
    <button
      class={selectedId === h.doc_id ? "row sel" : "row"}
      onclick={() => onSelect(h.doc_id)}
    >
      <span class="row-main">
        <span class="title">{h.title}</span>
        <span class="meta mono"><span class={statusTagClass(h.status)}>{h.status}</span><span class="src">{h.source_ref}</span></span>
      </span>
      <span class="snippet">{h.snippet}</span>
      <span class="tags">
        {#each h.tags as t (t.tag + t.kind)}
          <span class="tag">{t.tag}</span>
        {/each}
      </span>
    </button>
  {/each}
  {#if !searched && hits.length === 0}
    <li class="empty">Type a query to search knowledge.</li>
  {:else if searched && hits.length === 0}
    <li class="empty">No results.</li>
  {/if}
</ul>

<style>
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .row {
    display: flex;
    flex-direction: column;
    align-items: stretch;
    gap: 3px;
    width: 100%;
    padding: 5px 6px;
    font-size: 11px;
    border: none;
    border-bottom: 1px solid var(--hairline);
    background: none;
    color: inherit;
    text-align: left;
    cursor: pointer;
  }
  .row.sel {
    background: color-mix(in srgb, var(--accent) 10%, transparent);
  }
  .row-main {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 6px;
  }
  .title {
    color: var(--ink);
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
  }
  .meta {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    flex-shrink: 0;
  }
  .src {
    color: var(--faint);
    font-size: 9px;
  }
  .snippet {
    color: var(--body);
    font-size: 10px;
    line-height: 1.45;
    overflow: hidden;
    display: -webkit-box;
    line-clamp: 2;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
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
</style>
