<script lang="ts">
  import { onMount, tick } from "svelte";
  import { get, post, postBody } from "../lib/api";
  import { Button } from "$lib/components/ui/button";
  import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
  } from "$lib/components/ui/dialog";

  type ModeResponse = { mode: string; csrf_token: string | null };

  const MODES = ["OBSERVER", "PAPER", "LIVE"] as const;
  const LIVE_CONFIRM_TEXT = "LIVE";

  let mode = $state("OBSERVER");
  let showConfirm = $state(false);
  let typed = $state("");
  let error = $state("");
  let busy = $state(false);
  let confirmInput = $state<HTMLInputElement | null>(null);

  let isLive = $derived(mode === "LIVE");
  let canConfirm = $derived(typed.trim().toUpperCase() === LIVE_CONFIRM_TEXT);
  let modeKey = $derived(mode === "LIVE" ? "live" : mode === "PAPER" ? "paper" : "observer");

  onMount(() => {
    loadMode();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  });

  // Focus the typed-confirm input the moment the dialog opens so arming LIVE
  // is a single keystroke sequence away (type LIVE → Enter).
  $effect(() => {
    if (showConfirm) {
      tick().then(() => setTimeout(() => confirmInput?.focus(), 50));
    }
  });

  // Ctrl+M cycles OBSERVER → PAPER → LIVE → OBSERVER. Landing on LIVE routes
  // through the typed-confirm dialog. Never hijack while typing or when a
  // confirm dialog is already open.
  function onKey(event: KeyboardEvent): void {
    if (!event.ctrlKey || event.metaKey || event.altKey || event.key.toLowerCase() !== "m") return;
    const active = document.activeElement as HTMLElement | null;
    const typing =
      !!active &&
      (active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.isContentEditable);
    if (typing || showConfirm) return;
    event.preventDefault();
    cycleMode();
  }

  async function loadMode(): Promise<void> {
    try {
      const resp = await get<ModeResponse>("/api/execution/mode");
      mode = resp.mode;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  function cycleMode(): void {
    const idx = (MODES as readonly string[]).indexOf(mode);
    const next = idx >= 0 ? (MODES[(idx + 1) % MODES.length] ?? "OBSERVER") : "OBSERVER";
    select(next);
  }

  function select(target: string): void {
    if (target === mode) return;
    if (target === "LIVE") {
      typed = "";
      showConfirm = true;
    } else {
      void setMode(target);
    }
  }

  async function setMode(target: string): Promise<void> {
    error = "";
    busy = true;
    try {
      // LIVE requires the typed confirmation string "LIVE" in the request
      // body — a boolean query flag never arms LIVE (F-EXEC-001).
      const resp =
        target === "LIVE"
          ? await postBody<ModeResponse>("/api/execution/mode?mode=LIVE", {
              confirm: LIVE_CONFIRM_TEXT,
            })
          : await post<ModeResponse>(`/api/execution/mode?mode=${encodeURIComponent(target)}`);
      mode = resp.mode;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }

  function confirmLive(): void {
    showConfirm = false;
    void setMode("LIVE");
  }
</script>

<div class="mode-switcher" role="group" aria-label="Execution mode">
  <span
    class="mode-ind mode-{modeKey}"
    title="Current mode: {mode}. Ctrl+M cycles modes; LIVE requires confirmation."
  >
    <span class="mode-dot" aria-hidden="true"></span>
    <span class="mode-label">{mode}</span>
  </span>
  {#each MODES as m (m)}
    <Button
      variant={m === "LIVE" && isLive ? "default" : "outline"}
      size="sm"
      class={m === mode && m !== "LIVE"
        ? "border-accent-disabled bg-surface-elevated text-accent-active hover:bg-surface-elevated hover:text-accent-active"
        : ""}
      disabled={busy}
      onclick={() => select(m)}
      aria-pressed={m === mode}
    >
      {m}
      {#if m === "LIVE" && isLive}
        <span class="live-dot" aria-hidden="true"></span>
      {/if}
    </Button>
  {/each}
  {#if error}
    <span class="error" title={error}>ERR</span>
  {/if}
</div>

{#if isLive}
  <div class="live-banner" role="alert">
    <span class="banner-dot" aria-hidden="true"></span>
    <span class="banner-text">
      LIVE SESSION — real orders execute on approval. Nothing is placed
      automatically; confirm each proposal. Kill switch stays armed
      (Ctrl+Shift+K).
    </span>
  </div>
{/if}

<Dialog open={showConfirm} onOpenChange={(o) => !o && (showConfirm = false)}>
  <DialogContent class="live-confirm">
    <DialogHeader>
      <DialogTitle>Arm LIVE trading?</DialogTitle>
      <DialogDescription>
        LIVE mode places <strong class="danger-text">real orders</strong> on
        your connected brokerage account. Approved proposals execute
        immediately and cannot be undone.
      </DialogDescription>
    </DialogHeader>
    <div class="live-callout" role="note">
      <span>
        Type {LIVE_CONFIRM_TEXT} to arm. The kill switch stays active while
        trading — Ctrl+Shift+K disarms instantly.
      </span>
    </div>
    <input
      bind:this={confirmInput}
      bind:value={typed}
      class="live-input mono"
      type="text"
      placeholder={LIVE_CONFIRM_TEXT}
      aria-label="Type LIVE to confirm"
      autocapitalize="characters"
      spellcheck="false"
      onkeydown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          if (canConfirm) confirmLive();
        }
      }}
    />
    <DialogFooter>
      <Button variant="ghost" onclick={() => (showConfirm = false)} disabled={busy}>
        Cancel
      </Button>
      <Button variant="danger" onclick={confirmLive} disabled={busy || !canConfirm}>
        Arm LIVE
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>

<style>
  .mode-switcher {
    display: flex;
    align-items: center;
    gap: 4px;
    flex: none;
  }
  /* Mode indicator — OBSERVER = faint dot, PAPER = info dot, LIVE = accent dot
     pulsing 1s (DESIGN §4 mode indicator; DESIGN §5 header strip right side). */
  .mode-ind {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    margin-right: 2px;
    flex: none;
  }
  .mode-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--faint);
    flex: none;
  }
  .mode-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    white-space: nowrap;
  }
  .mode-observer .mode-dot {
    background: var(--faint);
  }
  .mode-observer .mode-label {
    color: var(--faint);
  }
  .mode-paper .mode-dot {
    background: var(--info);
  }
  .mode-paper .mode-label {
    color: var(--info);
  }
  .mode-live .mode-dot {
    background: var(--accent);
    animation: mode-pulse 1s ease-in-out infinite;
  }
  .mode-live .mode-label {
    color: var(--accent);
  }
  .live-dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    margin-left: 2px;
    background: var(--on-accent);
    animation: mode-pulse 1s ease-in-out infinite;
  }
  @keyframes mode-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.35;
    }
  }
  .error {
    color: var(--danger);
    font-size: 10px;
    margin-left: 8px;
  }
  /* LIVE session banner — full-width alert bar flush below the header.
     DESIGN §4 alert bar: 36px, danger at 10% on surface-card, border-bottom
     hairline-strong, leading dot + body text, no dismiss for danger. Top is
     coupled to App.svelte's --header-bottom measurement var (8px grid padding
     + 44px header strip) instead of JS measuring the header; App also reserves
     a 4th grid row below the bar while LIVE so the workspace is never covered.
     Non-interactive: pointer events pass through. */
  .live-banner {
    position: fixed;
    top: var(--header-bottom, 52px);
    left: 0;
    right: 0;
    z-index: 25;
    height: 36px;
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 0 14px;
    background: color-mix(in srgb, var(--danger) 10%, var(--surface-card));
    border-bottom: 1px solid var(--hairline-strong);
    color: var(--danger);
    pointer-events: none;
  }
  .banner-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--danger);
    flex: none;
    animation: mode-pulse 1s ease-in-out infinite;
  }
  .banner-text {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.03em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  /* Typed LIVE confirm — DESIGN §4 modal contract (surface-overlay bg,
     hairline-strong border, scrim) comes from the dialog primitive; the danger
     accents below mark this as the D10 risk surface. */
  .danger-text {
    color: var(--danger);
    font-weight: 700;
  }
  .live-callout {
    background: color-mix(in srgb, var(--danger) 10%, var(--surface-card));
    border: 1px solid var(--danger);
    border-radius: 4px;
    padding: 8px 10px;
    font-size: 11px;
    line-height: 1.5;
    color: var(--danger);
  }
  .live-input {
    width: 100%;
    background: var(--canvas-raised);
    border: 1px solid var(--hairline-strong);
    border-radius: 4px;
    color: var(--ink);
    padding: 8px 10px;
    font-size: 12px;
    text-transform: uppercase;
  }
  .live-input:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  @media (prefers-reduced-motion: reduce) {
    .mode-live .mode-dot,
    .live-dot,
    .banner-dot {
      animation: none;
    }
  }
</style>
