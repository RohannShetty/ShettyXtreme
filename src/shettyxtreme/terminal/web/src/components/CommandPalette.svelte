<script module lang="ts">
  // Module-scoped controller so the palette can be driven from outside without
  // a ref: App.svelte (integration phase) does
  //   import CommandPalette, { open, close } from "./components/CommandPalette.svelte"
  // and calls open() from its own shortcut/button. The store is the single
  // source of truth; the instance script below renders the Dialog off it.
  import { writable } from "svelte/store";

  export const paletteOpen = writable(false);

  export function open(): void {
    paletteOpen.set(true);
  }

  export function close(): void {
    paletteOpen.set(false);
  }
</script>

<script lang="ts">
  import { onMount, tick } from "svelte";
  import type { Component } from "svelte";
  import { computeCommandScore } from "bits-ui";
  import {
    Dialog,
    DialogContent,
    DialogTitle,
  } from "$lib/components/ui/dialog";
  import { Kbd } from "$lib/components/ui/kbd";
  import { activeTab, type CenterTabId } from "../lib/activeTab";
  import { applyTheme, getTheme, type Theme } from "../lib/theme";
  import {
    BookOpen,
    ChartBar,
    CornerDownLeft,
    FlaskConical,
    Lightbulb,
    List,
    Moon,
    RefreshCw,
    ScanLine,
    Search,
    Settings,
    Sun,
    Table2,
    Zap,
  } from "@lucide/svelte";

  type PaletteItem = {
    id: string;
    label: string;
    keywords: string[];
    hint: string;
    icon: Component;
    run: () => void;
  };

  // Right-dock panels (research, knowledge) live behind App.svelte's drawer
  // state, which this component must not touch. Navigation to them instead
  // dispatches the documented `sx:open-dock` window event — the integration
  // contract for App.svelte (see the wave-2 report §3).
  function openDock(): void {
    window.dispatchEvent(new CustomEvent("sx:open-dock"));
  }

  function goRoute(hash: string): void {
    window.location.hash = hash;
  }

  function goTab(tab: CenterTabId): void {
    activeTab.set(tab);
    goRoute("/");
  }

  const ITEMS: PaletteItem[] = [
    {
      id: "nav-watchlist",
      label: "Watchlist",
      keywords: ["rail", "symbols", "watch", "list", "instruments"],
      hint: "rail",
      icon: List,
      run: () => goRoute("/"),
    },
    {
      id: "nav-chain",
      label: "Chain",
      keywords: ["option", "strike", "greeks", "calls", "puts", "iv"],
      hint: "tab",
      icon: Table2,
      run: () => goTab("chain"),
    },
    {
      id: "nav-scanner",
      label: "Scanner",
      keywords: ["scan", "filter", "unusual", "activity", "momentum"],
      hint: "tab",
      icon: ScanLine,
      run: () => goTab("scanner"),
    },
    {
      id: "nav-hints",
      label: "Hints",
      keywords: ["suggestions", "coach", "setup", "strategy"],
      hint: "tab",
      icon: Lightbulb,
      run: () => goTab("hints"),
    },
    {
      id: "nav-analytics",
      label: "Analytics",
      keywords: ["regime", "stats", "iv", "data", "dashboard"],
      hint: "tab",
      icon: ChartBar,
      run: () => goTab("analytics"),
    },
    {
      id: "nav-research",
      label: "Research",
      keywords: ["brief", "deepseek", "report", "ai", "lens"],
      hint: "right dock",
      icon: FlaskConical,
      run: () => {
        goRoute("/");
        openDock();
      },
    },
    {
      id: "nav-knowledge",
      label: "Knowledge",
      keywords: ["kb", "docs", "search", "notes", "memory"],
      hint: "right dock",
      icon: BookOpen,
      run: () => {
        goRoute("/");
        openDock();
      },
    },
    {
      id: "nav-settings",
      label: "Settings",
      keywords: ["config", "credentials", "auth", "setup", "risk"],
      hint: "#/settings",
      icon: Settings,
      run: () => goRoute("/settings"),
    },
    {
      id: "act-theme",
      label: "Toggle theme",
      keywords: ["dark", "light", "appearance", "mode"],
      hint: "light/dark",
      icon: Sun,
      run: () => {
        const next: Theme = theme === "dark" ? "light" : "dark";
        applyTheme(next);
        theme = next;
      },
    },
    {
      id: "act-kill",
      label: "Toggle kill switch",
      keywords: ["arm", "disarm", "safety", "stop", "panic", "halt"],
      hint: "Ctrl+Shift+K",
      icon: Zap,
      // Disarm carries the typed-confirm safety flow (F-EXEC-001) owned by
      // KillSwitch.svelte — the palette never bypasses it, it just asks.
      run: () => window.dispatchEvent(new CustomEvent("sx:toggle-kill-switch")),
    },
    {
      id: "act-mode",
      label: "Cycle execution mode",
      keywords: ["observer", "paper", "live", "trading", "mode"],
      hint: "Ctrl+M",
      icon: RefreshCw,
      // LIVE arming routes through ModeSwitcher's typed-confirm dialog (D10).
      run: () => window.dispatchEvent(new CustomEvent("sx:cycle-mode")),
    },
  ];

  let query = $state("");
  let selected = $state(0);
  let inputEl = $state<HTMLInputElement | null>(null);

  // Theme state mirrors the header: Sun cross-fades in when dark (switch to
  // light), Moon when light. Read once on mount; the act-theme run handler
  // keeps it in sync (R7).
  let theme: Theme = $state(getTheme());

  let filtered = $derived.by(() => {
    const q = query.trim();
    if (!q) return ITEMS;
    return ITEMS
      .map((item) => ({
        item,
        score: computeCommandScore(item.label, q, item.keywords),
      }))
      .filter((x) => x.score > 0)
      .sort((a, b) => b.score - a.score)
      .map((x) => x.item);
  });

  // Focus the query input the moment the palette opens and reset the last
  // search, so Ctrl+K is always a clean slate (same 50ms settle as
  // ModeSwitcher's LIVE-confirm focus).
  $effect(() => {
    if ($paletteOpen) {
      query = "";
      selected = 0;
      tick().then(() => setTimeout(() => inputEl?.focus(), 50));
    }
  });

  function onInputKeydown(event: KeyboardEvent): void {
    const len = Math.max(filtered.length, 1);
    if (event.key === "ArrowDown") {
      event.preventDefault();
      selected = (selected + 1) % len;
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      selected = (selected - 1 + len) % len;
    } else if (event.key === "Enter") {
      event.preventDefault();
      runItem(filtered[selected]);
    }
  }

  function runItem(item: PaletteItem | undefined): void {
    if (!item) return;
    close();
    item.run();
  }

  // Ctrl+K / ⌘K opens (or closes) the palette. Never hijacks while the
  // operator is typing in an input/textarea (same guard as KnowledgePanel's
  // Ctrl+F and ShortcutsDialog's Ctrl+/); Ctrl+Shift+K is left to the kill
  // switch. Mounting <CommandPalette /> alone enables the shortcut.
  function onGlobalKey(event: KeyboardEvent): void {
    if (!(event.ctrlKey || event.metaKey) || event.altKey || event.shiftKey) return;
    if (event.key.toLowerCase() !== "k") return;
    const active = document.activeElement as HTMLElement | null;
    const typing =
      !!active &&
      (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.isContentEditable);
    if (!$paletteOpen && typing) return;
    event.preventDefault();
    if ($paletteOpen) {
      close();
    } else {
      open();
    }
  }

  onMount(() => {
    window.addEventListener("keydown", onGlobalKey);
    return () => {
      window.removeEventListener("keydown", onGlobalKey);
    };
  });
</script>

<Dialog open={$paletteOpen} onOpenChange={(o) => !o && close()}>
  <DialogContent class="w-[min(560px,90vw)] gap-0 overflow-hidden p-0">
    <DialogTitle class="sr-only">Command palette</DialogTitle>

    <div class="palette-input">
      <Search class="size-4 text-faint" aria-hidden="true" />
      <input
        bind:this={inputEl}
        bind:value={query}
        class="palette-query mono"
        type="text"
        placeholder="Type a command…"
        role="combobox"
        aria-label="Command palette"
        aria-expanded="true"
        aria-controls="palette-results"
        aria-activedescendant={filtered[selected]
          ? `palette-item-${filtered[selected].id}`
          : undefined}
        autocomplete="off"
        autocapitalize="off"
        spellcheck="false"
        onkeydown={onInputKeydown}
        oninput={() => (selected = 0)}
      />
    </div>

    <ul class="palette-list" id="palette-results" role="listbox" aria-label="Commands">
      {#if filtered.length === 0}
        <li class="empty">No commands match “{query}”.</li>
      {:else}
        {#each filtered as item, i (item.id)}
          {@const Icon = item.icon}
          <li>
            <button
              type="button"
              role="option"
              id="palette-item-{item.id}"
              aria-selected={i === selected}
              class="palette-item"
              class:sel={i === selected}
              onclick={() => runItem(item)}
              onmouseenter={() => (selected = i)}
            >
              {#if item.id === "act-theme"}
              <span class="relative inline-flex size-3.5" aria-hidden="true">
                <Sun
                  class="absolute inset-0 size-3.5 transition-[opacity,filter,scale] duration-300 ease-[cubic-bezier(0.2,0,0,1)] {i === selected ? 'text-accent' : 'text-muted-foreground'} {theme === 'dark' ? 'opacity-100 scale-100 blur-0' : 'opacity-0 scale-[0.25] blur-[4px]'}"
                />
                <Moon
                  class="absolute inset-0 size-3.5 transition-[opacity,filter,scale] duration-300 ease-[cubic-bezier(0.2,0,0,1)] {i === selected ? 'text-accent' : 'text-muted-foreground'} {theme === 'dark' ? 'opacity-0 scale-[0.25] blur-[4px]' : 'opacity-100 scale-100 blur-0'}"
                />
              </span>
            {:else}
              <Icon class={i === selected ? "size-3.5 text-accent" : "size-3.5 text-muted-foreground"} />
            {/if}
              <span class="item-label">{item.label}</span>
              <span class="item-hint mono">{item.hint}</span>
            </button>
          </li>
        {/each}
      {/if}
    </ul>

    <div class="palette-foot mono" aria-hidden="true">
      <Kbd class="px-1">↑↓</Kbd>
      <span class="foot-hint">navigate</span>
      <Kbd><CornerDownLeft class="size-3" /></Kbd>
      <span class="foot-hint">select</span>
      <Kbd>Esc</Kbd>
      <span class="foot-hint">close</span>
    </div>
  </DialogContent>
</Dialog>

<style>
  /* Command palette — DESIGN.md §6 level-3 overlay: surface-overlay +
     hairline-strong + scrim come from the dialog primitive. The query field is
     command/terminal text → mono face (DESIGN §3). Layout: input on top,
     results below, key hints in the foot. */
  .palette-input {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 12px;
    border-bottom: 1px solid var(--hairline-strong);
  }
  .palette-input:focus-within {
    border-bottom-color: var(--accent);
  }
  .palette-query {
    flex: 1;
    min-width: 0;
    background: transparent;
    border: none;
    padding: 0;
    color: var(--ink);
    font-size: 13px;
    outline: none;
  }
  .palette-query::placeholder {
    color: var(--faint);
  }
  .palette-list {
    margin: 0;
    padding: 4px;
    list-style: none;
    overflow-y: auto;
    max-height: min(340px, 55vh);
  }
  .palette-item {
    display: flex;
    align-items: center;
    gap: 10px;
    width: 100%;
    padding: 7px 10px;
    background: transparent;
    border: none;
    border-left: 2px solid transparent;
    border-radius: 4px;
    color: var(--ink);
    cursor: pointer;
    text-align: left;
  }
  .palette-item:hover {
    background: var(--row-hover);
  }
  /* Selected row: row-selected fill + accent edge (DESIGN §2.4 selected row). */
  .palette-item.sel {
    background: var(--row-selected);
    border-left-color: var(--accent);
  }
  .item-label {
    flex: 1;
    min-width: 0;
    font-size: 13px;
    color: var(--ink);
  }
  .item-hint {
    font-size: 10px;
    color: var(--faint);
    flex: none;
  }
  .palette-foot {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 12px;
    border-top: 1px solid var(--hairline);
    color: var(--faint);
    font-size: 10px;
  }
  .foot-hint {
    margin-right: 4px;
  }
  .empty {
    padding: 18px 12px;
    color: var(--faint);
    font-size: 12px;
    text-align: center;
  }
</style>
