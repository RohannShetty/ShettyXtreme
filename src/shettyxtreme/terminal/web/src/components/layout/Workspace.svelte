<!-- Workspace — resizable 3-col layout (rail | gutter | center | gutter | right).
     Extracted from App.svelte (lines 33–111 for JS, 396–611 for CSS).
     Rail and right-dock widths are CSS custom props on .workspace so the grid
     tracks track them; the 8px gutter columns replace the old 8px column gap.
     Widths persist to localStorage, clamped to [min, min(hard-max, 0.5×vw)]
     on restore.  Below 1440px the right dock becomes the overlay drawer and
     its gutter + width are unused (media query). -->
<script lang="ts">
  import type { Snippet } from "svelte";
  import { Kbd } from "$lib/components/ui/kbd";
  import { Separator } from "$lib/components/ui/separator";
  import { X } from "@lucide/svelte";

  interface Props {
    drawerOpen: boolean;
    rail: Snippet;
    center: Snippet;
    rightDock: Snippet;
  }

  let { drawerOpen = $bindable(false), rail, center, rightDock }: Props = $props();

  // ── Resizable split panes (recon §1.3, ARCHITECTURE_V2 §15) ─────────────
  const RAIL_MIN = 260;
  const RAIL_MAX = 480;
  const RIGHT_MIN = 320;
  const RIGHT_MAX = 640;
  const RAIL_KEY = "sx:rail-w";
  const RIGHT_KEY = "sx:right-w";

  let railW = $state(loadPaneWidth(RAIL_KEY, RAIL_MIN, RAIL_MIN, RAIL_MAX));
  let rightW = $state(loadPaneWidth(RIGHT_KEY, RIGHT_MIN, RIGHT_MIN, RIGHT_MAX));
  let drag: { kind: "rail" | "right"; startX: number; startW: number } | null = $state(null);

  function loadPaneWidth(key: string, fallback: number, min: number, max: number): number {
    try {
      const raw = Number(localStorage.getItem(key));
      if (!Number.isFinite(raw) || raw <= 0) return fallback;
      return clampPane(raw, min, max);
    } catch {
      return fallback;
    }
  }

  function clampPane(value: number, min: number, max: number): number {
    const upper = Math.max(min, Math.min(max, 0.5 * window.innerWidth));
    return Math.min(Math.max(value, min), upper);
  }

  function persistPane(key: string, value: number): void {
    try {
      localStorage.setItem(key, String(Math.round(value)));
    } catch {
      /* storage unavailable — resizing still applies for the session */
    }
  }

  function onGutterPointerDown(kind: "rail" | "right", event: PointerEvent): void {
    event.preventDefault();
    const el = event.currentTarget as HTMLElement;
    el.setPointerCapture(event.pointerId);
    drag = { kind, startX: event.clientX, startW: kind === "rail" ? railW : rightW };
  }

  function onGutterPointerMove(event: PointerEvent): void {
    if (!drag) return;
    const delta = event.clientX - drag.startX;
    if (drag.kind === "rail") {
      railW = clampPane(drag.startW + delta, RAIL_MIN, RAIL_MAX);
    } else {
      rightW = clampPane(drag.startW - delta, RIGHT_MIN, RIGHT_MAX);
    }
  }

  function onGutterPointerUp(): void {
    if (!drag) return;
    persistPane(RAIL_KEY, railW);
    persistPane(RIGHT_KEY, rightW);
    drag = null;
  }

  // Keyboard nudge on the separator (focusable, role=separator): ←/→ steps
  // the boundary by 8px and persists immediately.
  function onGutterKeydown(kind: "rail" | "right", event: KeyboardEvent): void {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const step = event.key === "ArrowRight" ? 8 : -8;
    if (kind === "rail") {
      railW = clampPane(railW + step, RAIL_MIN, RAIL_MAX);
      persistPane(RAIL_KEY, railW);
    } else {
      rightW = clampPane(rightW - step, RIGHT_MIN, RIGHT_MAX);
      persistPane(RIGHT_KEY, rightW);
    }
  }
</script>

<div
  class="workspace"
  style="--rail-w: {railW}px; --right-w: {rightW}px"
  class:dragging={drag !== null}
>
  <div class="rail">
    {@render rail()}
  </div>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <!-- Focusable role="separator" with arrow-key resize is the WAI-ARIA resizable
       separator widget; svelte-check's interactive-role list predates it. -->
  <div
    class="gutter"
    class:drag-active={drag?.kind === "rail"}
    role="separator"
    aria-orientation="vertical"
    aria-label="Resize watchlist"
    aria-valuenow={railW}
    aria-valuemin={RAIL_MIN}
    aria-valuemax={RAIL_MAX}
    tabindex="0"
    onpointerdown={(e) => onGutterPointerDown("rail", e)}
    onpointermove={onGutterPointerMove}
    onpointerup={onGutterPointerUp}
    onpointercancel={onGutterPointerUp}
    onkeydown={(e) => onGutterKeydown("rail", e)}
  >
    <span class="gutter-line" aria-hidden="true"></span>
  </div>
  <div class="center">
    {@render center()}
  </div>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <!-- Focusable role="separator" with arrow-key resize is the WAI-ARIA resizable
       separator widget; svelte-check's interactive-role list predates it. -->
  <div
    class="gutter gutter-right"
    class:drag-active={drag?.kind === "right"}
    role="separator"
    aria-orientation="vertical"
    aria-label="Resize right dock"
    aria-valuenow={rightW}
    aria-valuemin={RIGHT_MIN}
    aria-valuemax={RIGHT_MAX}
    tabindex="0"
    onpointerdown={(e) => onGutterPointerDown("right", e)}
    onpointermove={onGutterPointerMove}
    onpointerup={onGutterPointerUp}
    onpointercancel={onGutterPointerUp}
    onkeydown={(e) => onGutterKeydown("right", e)}
  >
    <span class="gutter-line" aria-hidden="true"></span>
  </div>
  <div class="right-col" class:open={drawerOpen}>
    <header class="drawer-head">
      <h2>Right Dock</h2>
      <div class="drawer-head-actions">
        <Kbd>Ctrl+R</Kbd>
        <button
          class="drawer-close"
          onclick={() => (drawerOpen = false)}
          aria-label="Close right dock"
        >
          <X class="size-4" />
        </button>
      </div>
    </header>
    <div class="drawer-sep" aria-hidden="true">
      <Separator />
    </div>
    {@render rightDock()}
  </div>
</div>

<style>
  /* 3-col workspace: rail | gutter | center | gutter | right-col (DESIGN §5/§15,
     recon §1.3). The 8px gutter columns replace the old 8px column gap — the
     spacing is byte-identical, but the gutter gives a drag handle (pointer
     events, rail/right widths clamped + persisted). No overflow-x here — every
     panel scrolls inside itself (DESIGN §8). */
  .workspace {
    display: grid;
    grid-template-columns: var(--rail-w, 260px) 8px minmax(0, 1fr) 8px var(--right-w, 320px);
    gap: 0;
    min-height: 0;
    overflow: hidden;
  }
  .workspace.dragging {
    user-select: none;
  }
  .gutter {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: col-resize;
    touch-action: none;
    outline: none;
  }
  .gutter:focus-visible {
    box-shadow: inset 0 0 0 2px var(--focus-ring);
  }
  .gutter-line {
    width: 2px;
    height: 28px;
    border-radius: 1px;
    background: var(--hairline-strong);
    opacity: 0;
    transition: opacity 100ms ease-out;
  }
  .gutter:hover .gutter-line,
  .gutter:focus-visible .gutter-line,
  .gutter.drag-active .gutter-line {
    opacity: 1;
  }
  .gutter.drag-active .gutter-line,
  .gutter:active .gutter-line {
    background: var(--accent);
  }
  .rail {
    min-width: 260px;
    min-height: 0;
    border-radius: 8px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
    overflow: hidden;
  }
  .center {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
  }
  .right-col {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 320px;
    min-height: 0;
    overflow: hidden;
    border-radius: 8px;
  }
  /* Drawer chrome — only rendered in overlay mode below 1440px. */
  .drawer-head {
    display: none;
    align-items: center;
    justify-content: space-between;
    padding: 6px 10px;
    background: var(--surface-elevated);
    border: 1px solid var(--hairline-strong);
    border-radius: 6px 6px 0 0;
  }
  .drawer-head h2 {
    margin: 0;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .drawer-head-actions {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .drawer-sep {
    display: none;
  }
  .drawer-close {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: none;
    border: none;
    color: var(--faint);
    cursor: pointer;
    /* R5: 6px padding around the size-4 icon → ~28px target inside the
       44px drawer header. */
    padding: 6px;
  }
  .drawer-close:hover {
    color: var(--ink);
  }

  @media (max-width: 1439px) {
    .workspace {
      grid-template-columns: var(--rail-w, 260px) 8px minmax(0, 1fr);
    }
    /* Right dock is no longer a grid column below 1440px — its gutter (and the
       persisted --right-w) is unused until the viewport grows back. */
    .gutter-right {
      display: none;
    }
    /* Right dock becomes a level-3 overlay drawer: surface-overlay +
       hairline-strong, no drop shadow (DESIGN §6). Toggle: Ctrl+R, Esc,
       the header logs button, or the drawer's own close. */
    .right-col {
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      z-index: 30;
      width: min(380px, 88vw);
      min-width: min(380px, 88vw);
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 8px;
      background: var(--surface-overlay);
      border-left: 1px solid var(--hairline-strong);
      border-radius: 0;
      transform: translateX(100%);
      /* R10: hidden while off-screen so the four docked panels (Research,
         Knowledge — the heavy ones) skip paint in the default closed state.
         visibility transitions discretely: flips to visible on open-start,
         holds visible through the 120ms slide-out, then flips hidden. The
         keep-alive DOM + WS state stays intact. */
      visibility: hidden;
      transition: transform 120ms ease-out, visibility 120ms;
    }
    .right-col.open {
      transform: translateX(0);
      visibility: visible;
    }
    .drawer-head {
      display: flex;
    }
    .drawer-sep {
      display: block;
    }
  }
</style>
