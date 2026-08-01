<script lang="ts">
  import { onMount } from "svelte";
  import { get, post } from "../lib/api";

  type ModeResponse = { mode: string };

  const MODES = ["OBSERVER", "PAPER", "LIVE"];

  let mode = "OBSERVER";
  let showConfirm = false;
  let error = "";

  $: isLive = mode === "LIVE";

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
    const qs = target === "LIVE" ? "?mode=LIVE&confirm=true" : `?mode=${encodeURIComponent(target)}`;
    try {
      const resp = await post<ModeResponse>(`/api/execution/mode${qs}`);
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
    <button
      class="mode-btn"
      class:active={m === mode}
      class:live={m === "LIVE" && isLive}
      on:click={() => select(m)}
    >
      {m}
      {#if m === "LIVE" && isLive}
        <span class="live-dot" aria-hidden="true"></span>
      {/if}
    </button>
  {/each}
  {#if error}
    <span class="error" title={error}>ERR</span>
  {/if}
</div>

{#if showConfirm}
  <div class="scrim" role="presentation" on:click={() => (showConfirm = false)}></div>
  <div class="dialog" role="dialog" aria-modal="true" aria-labelledby="live-title">
    <h3 id="live-title">Switch to LIVE mode?</h3>
    <p>LIVE mode places real orders. This is an explicit per-session action — confirm to proceed.</p>
    <div class="dialog-actions">
      <button class="btn ghost" on:click={() => (showConfirm = false)}>Cancel</button>
      <button class="btn danger" on:click={confirmLive}>Confirm LIVE</button>
    </div>
  </div>
{/if}

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
  .mode-btn {
    position: relative;
    background: var(--surface-card);
    color: var(--muted);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.04em;
    cursor: pointer;
  }
  .mode-btn:hover {
    color: var(--body);
    border-color: var(--hairline-strong);
  }
  .mode-btn.active {
    color: var(--accent-active);
    border-color: var(--accent-disabled);
    background: var(--surface-elevated);
  }
  .mode-btn.live {
    color: var(--on-accent);
    background: var(--accent);
    border-color: var(--accent);
  }
  .live-dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    margin-left: 6px;
    background: var(--accent-active);
    box-shadow: 0 0 6px var(--accent);
    animation: pulse 1.2s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.35; }
  }
  .error {
    color: var(--danger);
    font-size: 10px;
    margin-left: 8px;
  }
  .scrim {
    position: fixed;
    inset: 0;
    background: var(--scrim);
    z-index: 40;
  }
  .dialog {
    position: fixed;
    z-index: 41;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: min(420px, 90vw);
    background: var(--surface-overlay);
    border: 1px solid var(--hairline-strong);
    border-radius: 6px;
    padding: 16px;
  }
  .dialog h3 {
    margin: 0 0 8px;
    color: var(--ink);
    font-size: 14px;
  }
  .dialog p {
    margin: 0 0 14px;
    color: var(--muted);
    line-height: 1.5;
  }
  .dialog-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
  .btn {
    border-radius: 4px;
    border: 1px solid var(--hairline-strong);
    background: var(--surface-card);
    color: var(--body);
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
  }
  .btn.ghost:hover {
    color: var(--ink);
    border-color: var(--muted);
  }
  .btn.danger {
    background: var(--danger);
    border-color: var(--danger);
    color: #fff;
  }
</style>
