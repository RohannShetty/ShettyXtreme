<script lang="ts">
  import { onMount } from "svelte";
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

  const MODES = ["OBSERVER", "PAPER", "LIVE"];

  let mode = $state("OBSERVER");
  let showConfirm = $state(false);
  let error = $state("");

  let isLive = $derived(mode === "LIVE");

  onMount(() => {
    loadMode();
  });

  async function loadMode(): Promise<void> {
    try {
      const resp = await get<ModeResponse>("/api/execution/mode");
      mode = resp.mode;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  function select(target: string): void {
    if (target === mode) return;
    if (target === "LIVE") {
      showConfirm = true;
    } else {
      setMode(target);
    }
  }

  async function setMode(target: string): Promise<void> {
    error = "";
    try {
      // LIVE requires the typed confirmation string "LIVE" in the request
      // body — a boolean query flag never arms LIVE (F-EXEC-001).
      const resp =
        target === "LIVE"
          ? await postBody<ModeResponse>("/api/execution/mode?mode=LIVE", { confirm: "LIVE" })
          : await post<ModeResponse>(`/api/execution/mode?mode=${encodeURIComponent(target)}`);
      mode = resp.mode;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  function confirmLive(): void {
    showConfirm = false;
    setMode("LIVE");
  }
</script>

<div class="mode-switcher">
  <span class="label">MODE</span>
  {#each MODES as m (m)}
    <Button
      variant={m === "LIVE" && isLive ? "default" : "outline"}
      size="sm"
      class={m === mode && m !== "LIVE"
        ? "border-accent-disabled bg-surface-elevated text-accent-active hover:bg-surface-elevated hover:text-accent-active"
        : ""}
      onclick={() => select(m)}
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

<Dialog open={showConfirm} onOpenChange={(o) => (showConfirm = o)}>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Switch to LIVE mode?</DialogTitle>
      <DialogDescription>
        LIVE mode places real orders. This is an explicit per-session action — confirm to proceed.
      </DialogDescription>
    </DialogHeader>
    <DialogFooter>
      <Button variant="ghost" onclick={() => (showConfirm = false)}>Cancel</Button>
      <Button variant="danger" onclick={confirmLive}>Confirm LIVE</Button>
    </DialogFooter>
  </DialogContent>
</Dialog>

<style>
  .mode-switcher {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .label {
    font-size: 10px;
    letter-spacing: 0.08em;
    color: var(--muted);
    margin-right: 4px;
  }
  .live-dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    margin-left: 2px;
    background: var(--on-accent);
    animation: pulse 1.2s ease-in-out infinite;
  }
  @keyframes pulse {
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
</style>
