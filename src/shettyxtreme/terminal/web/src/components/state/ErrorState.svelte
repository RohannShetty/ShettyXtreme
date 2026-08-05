<script lang="ts">
  import { Button } from "$lib/components/ui/button";

  let {
    message = "Something went wrong.",
    onRetry,
  }: {
    message?: string;
    onRetry?: () => void;
  } = $props();
</script>

<div class="error" role="alert">
  <span class="dot" aria-hidden="true"></span>
  <p class="msg">{message}</p>
  {#if onRetry}
    <Button variant="secondary" size="sm" class="shrink-0" onclick={onRetry}>Retry</Button>
  {/if}
</div>

<style>
  .error {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    background: color-mix(in srgb, var(--danger) 10%, transparent);
    border: 1px solid var(--danger);
    border-radius: 4px;
  }
  .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--danger);
    flex: none;
  }
  .msg {
    margin: 0;
    flex: 1;
    min-width: 0;
    color: var(--danger);
    font-size: 11px;
    line-height: 16px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
</style>
