<script lang="ts">
  import { get } from "../lib/api";

  type SymbolHit = {
    internal_symbol: string;
    fyers_symbol: string;
    exchange: string;
    instrument_type: string;
    expiry: string | null;
    strike: number | null;
    option_type: string | null;
    lot_size: number | null;
    tick_size: number | null;
  };

  type SymbolSearchResponse = {
    query: string;
    canonical: string;
    hits: SymbolHit[];
  };

  type Props = {
    value?: string;
    placeholder?: string;
    class?: string;
    onSelect?: (hit: SymbolHit) => void;
    onInput?: (value: string) => void;
  };

  let {
    value = $bindable(""),
    placeholder = "SYMBOL",
    class: className = "",
    onSelect,
    onInput,
  }: Props = $props();

  let hits: SymbolHit[] = $state([]);
  let activeIndex = $state(-1);
  let open = $state(false);
  let searching = $state(false);
  let debounceTimer: number | undefined;
  let wrapEl: HTMLDivElement | undefined;
  let listEl: HTMLUListElement | undefined;

  async function search(): Promise<void> {
    const q = value.trim();
    if (!q) {
      hits = [];
      open = false;
      return;
    }
    if (searching) return;
    searching = true;
    try {
      const resp = await get<SymbolSearchResponse>(
        `/api/symbols/search?q=${encodeURIComponent(q)}&limit=10`,
      );
      hits = resp.hits;
      open = hits.length > 0;
      activeIndex = -1;
    } catch {
      hits = [];
      open = false;
    } finally {
      searching = false;
    }
  }

  function onInputHandler(): void {
    onInput?.(value);
    if (debounceTimer !== undefined) window.clearTimeout(debounceTimer);
    debounceTimer = window.setTimeout(() => {
      search();
    }, 300);
  }

  function onKeydown(event: KeyboardEvent): void {
    if (!open || hits.length === 0) {
      if (event.key === "Enter") {
        if (debounceTimer !== undefined) window.clearTimeout(debounceTimer);
        search();
      }
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      activeIndex = Math.min(activeIndex + 1, hits.length - 1);
      scrollIntoView();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      activeIndex = Math.max(activeIndex - 1, 0);
      scrollIntoView();
    } else if (event.key === "Enter") {
      event.preventDefault();
      if (activeIndex >= 0 && activeIndex < hits.length) {
        selectHit(hits[activeIndex]);
      }
    } else if (event.key === "Escape") {
      open = false;
      activeIndex = -1;
    }
  }

  function scrollIntoView(): void {
    if (!listEl) return;
    const el = listEl.children[activeIndex] as HTMLElement | undefined;
    el?.scrollIntoView({ block: "nearest" });
  }

  function selectHit(hit: SymbolHit): void {
    value = hit.internal_symbol;
    open = false;
    activeIndex = -1;
    hits = [];
    onSelect?.(hit);
  }

  function onBlur(): void {
    // Delay close so click events on the dropdown can fire first
    setTimeout(() => {
      open = false;
    }, 200);
  }

  function formatMeta(hit: SymbolHit): string {
    const parts = [hit.exchange, hit.instrument_type];
    if (hit.lot_size) parts.push(`lot:${hit.lot_size}`);
    return parts.join(" · ");
  }
</script>

<div class="symbol-search {className}" bind:this={wrapEl}>
  <input
    type="text"
    class="search-input mono"
    {placeholder}
    bind:value
    oninput={onInputHandler}
    onkeydown={onKeydown}
    onfocus={() => { if (hits.length > 0) open = true; }}
    onblur={onBlur}
    autocomplete="off"
    spellcheck="false"
  />
  {#if open && hits.length > 0}
    <ul class="dropdown" bind:this={listEl}>
      {#each hits as hit, i (hit.fyers_symbol)}
        <li
          class="hit"
          class:active={i === activeIndex}
          onmousedown={(e) => { e.preventDefault(); selectHit(hit); }}
          onmouseenter={() => (activeIndex = i)}
          role="option"
          aria-selected={i === activeIndex}
        >
          <span class="sym">{hit.internal_symbol}</span>
          <span class="meta">{formatMeta(hit)}</span>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .symbol-search {
    position: relative;
    flex: 1;
    min-width: 0;
  }
  .search-input {
    width: 100%;
    height: 28px;
    padding: 0 6px;
    font-size: 12px;
    background: var(--surface);
    border: 1px solid var(--hairline);
    border-radius: 3px;
    color: var(--ink);
    outline: none;
  }
  .search-input:focus {
    border-color: var(--accent);
    box-shadow: 0 0 0 1px var(--focus-ring);
  }
  .search-input::placeholder {
    color: var(--faint);
  }
  .dropdown {
    position: absolute;
    top: 100%;
    left: 0;
    right: 0;
    z-index: 50;
    margin: 2px 0 0;
    padding: 2px 0;
    list-style: none;
    background: var(--surface);
    border: 1px solid var(--hairline);
    border-radius: 3px;
    max-height: 200px;
    overflow-y: auto;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
  }
  .hit {
    display: flex;
    align-items: center;
    gap: 8px;
    height: 26px;
    padding: 0 8px;
    cursor: pointer;
    font-size: 12px;
  }
  .hit:hover,
  .hit.active {
    background: var(--row-hover);
  }
  .sym {
    font-weight: 600;
    color: var(--ink);
    white-space: nowrap;
  }
  .meta {
    font-size: 10px;
    color: var(--faint);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
