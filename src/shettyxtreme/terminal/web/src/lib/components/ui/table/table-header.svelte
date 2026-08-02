<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children }: Props = $props();
</script>

<thead class={cn("sticky top-0 z-1 bg-canvas-raised", className)}>
  {#if children}
    {@render children()}
  {/if}
</thead>
