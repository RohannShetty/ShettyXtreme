<script lang="ts">
  import { Button } from "$lib/components/ui/button";

  let {
    message = "No data.",
    actionLabel,
    onAction,
  }: {
    message?: string;
    actionLabel?: string;
    onAction?: () => void;
  } = $props();
</script>

<div class="empty" role="status">
  <p class="msg">{message}</p>
  {#if actionLabel && onAction}
    <Button variant="secondary" size="sm" onclick={onAction}>{actionLabel}</Button>
  {/if}
</div>

<style>
  .empty {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 10px;
    padding: 16px 12px;
  }
  .msg {
    margin: 0;
    color: var(--faint);
    font-size: 11px;
    line-height: 16px;
  }
</style>
