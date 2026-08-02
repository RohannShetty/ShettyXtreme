<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { get, post } from "../lib/api";
  import { Button } from "$lib/components/ui/button";

  type KillSwitchResponse = { active: boolean };

  let armed = $state(false);
  let error = $state("");

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

<Button
  variant="danger"
  class={armed ? "kill-pulse min-h-9 whitespace-nowrap tracking-[0.05em]" : "min-h-9 whitespace-nowrap tracking-[0.05em]"}
  onclick={toggle}
  title="Toggle kill switch (Ctrl+Shift+K)"
  type="button"
>
  {armed ? "KILL SWITCH ARMED" : "KILL SWITCH OFF"}
</Button>
{#if error}
  <span class="error" title={error}>ERR</span>
{/if}

<style>
  .error {
    color: var(--danger);
    font-size: 10px;
    margin-left: 8px;
  }
</style>
