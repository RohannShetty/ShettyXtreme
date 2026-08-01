<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { get, post } from "../lib/api";

  type KillSwitchResponse = { active: boolean };

  let armed = false;
  let error = "";

  onMount(() => {
    loadState();
    window.addEventListener("keydown", onKey);
  });

  onDestroy(() => {
    window.removeEventListener("keydown", onKey);
  });

  function onKey(event: KeyboardEvent): void {
    if (event.ctrlKey && event.shiftKey && (event.key === "K" || event.key === "k")) {
      event.preventDefault();
      toggle();
    }
  }

  async function loadState(): Promise<void> {
    try {
      const resp = await get<KillSwitchResponse>("/api/execution/kill-switch");
      armed = resp.active;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function toggle(): Promise<void> {
    try {
      const resp = await post<KillSwitchResponse>(`/api/execution/kill-switch?activate=${!armed}`);
      armed = resp.active;
      error = "";
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }
</script>

<button
  class="kill"
  class:armed
  on:click={toggle}
  title="Toggle kill switch (Ctrl+Shift+K)"
  type="button"
>
  {armed ? "KILL SWITCH ARMED" : "KILL SWITCH OFF"}
</button>
{#if error}
  <span class="error" title={error}>ERR</span>
{/if}

<style>
  .kill {
    background: var(--surface-card);
    color: var(--muted);
    border: 1px solid var(--danger);
    border-radius: 4px;
    padding: 5px 12px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.05em;
    cursor: pointer;
    white-space: nowrap;
  }
  .kill:hover {
    color: var(--danger);
  }
  .kill.armed {
    background: var(--danger);
    border-color: var(--danger);
    color: #fff;
    animation: pulse 1.4s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(229, 72, 77, 0.5); }
    50% { box-shadow: 0 0 0 5px rgba(229, 72, 77, 0); }
  }
  .error {
    color: var(--danger);
    font-size: 10px;
    margin-left: 8px;
  }
</style>
