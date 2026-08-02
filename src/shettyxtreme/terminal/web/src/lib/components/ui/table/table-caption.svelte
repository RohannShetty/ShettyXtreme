<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children }: Props = $props();
</script>

<caption class={cn("mt-4 text-sm text-muted-foreground", className)}>
  {#if children}
    {@render children()}
  {/if}
</caption>
