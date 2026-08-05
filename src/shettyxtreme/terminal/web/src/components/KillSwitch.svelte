<script lang="ts">
  import { onDestroy, onMount } from "svelte";
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

  type KillSwitchResponse = { active: boolean };

  const DISARM_CONFIRM_TEXT = "DISARM";

  let armed = $state(false);
  let error = $state("");
  let disarmOpen = $state(false);
  let typed = $state("");
  let busy = $state(false);

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

  function toggle(): void {
    if (armed) {
      // Disarming re-arms trading: requires typed confirmation (F-EXEC-001).
      typed = "";
      disarmOpen = true;
    } else {
      doArm();
    }
  }

  async function doArm(): Promise<void> {
    busy = true;
    try {
      const resp = await post<KillSwitchResponse>("/api/execution/kill-switch?activate=true");
      armed = resp.active;
      error = "";
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }

  async function doDisarm(): Promise<void> {
    busy = true;
    try {
      const resp = await postBody<KillSwitchResponse>(
        "/api/execution/kill-switch?activate=false",
        { confirm: typed },
      );
      armed = resp.active;
      error = "";
      disarmOpen = false;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
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

<Dialog open={disarmOpen} onOpenChange={(o) => !o && (disarmOpen = false)}>
  <DialogContent>
    <DialogHeader>
      <DialogTitle>Disarm kill switch?</DialogTitle>
      <DialogDescription>
        Disarming re-enables order placement. Type {DISARM_CONFIRM_TEXT} to confirm.
      </DialogDescription>
    </DialogHeader>
    <input
      class="disarm-input mono"
      type="text"
      bind:value={typed}
      placeholder={DISARM_CONFIRM_TEXT}
      onkeydown={(e) => e.key === "Enter" && typed === DISARM_CONFIRM_TEXT && doDisarm()}
    />
    <DialogFooter>
      <Button variant="ghost" onclick={() => (disarmOpen = false)} disabled={busy}>Cancel</Button>
      <Button
        variant="danger"
        onclick={doDisarm}
        disabled={busy || typed !== DISARM_CONFIRM_TEXT}
      >
        Disarm
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>

<style>
  .error {
    color: var(--danger);
    font-size: 10px;
    margin-left: 8px;
  }
  .disarm-input {
    width: 100%;
    background: var(--canvas-raised);
    border: 1px solid var(--hairline-strong);
    border-radius: 4px;
    color: var(--ink);
    padding: 8px 10px;
    font-size: 12px;
  }
</style>
