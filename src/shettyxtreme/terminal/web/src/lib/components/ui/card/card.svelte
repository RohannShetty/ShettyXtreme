<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children }: Props = $props();
</script>

<div class={cn("rounded-[6px] border border-hairline bg-surface-card text-body", className)}>
  {#if children}
    {@render children()}
  {/if}
</div>
