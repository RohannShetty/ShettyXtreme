<script lang="ts">
  let {
    label = "Loading…",
    rows = 3,
  }: { label?: string; rows?: number } = $props();
</script>

<div class="loading" role="status" aria-live="polite">
  <div class="bars" aria-hidden="true">
    {#each Array.from({ length: rows }) as _, i (i)}
      <div class="bar" style="width: {100 - i * 15}%"></div>
    {/each}
  </div>
  <p class="label">{label}</p>
</div>

<style>
  .loading {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 16px 12px;
  }
  .bars {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .bar {
    height: 10px;
    border-radius: 4px;
    background: var(--surface-elevated);
    border: 1px solid var(--hairline);
  }
  .label {
    margin: 0;
    color: var(--faint);
    font-size: 11px;
  }
</style>
