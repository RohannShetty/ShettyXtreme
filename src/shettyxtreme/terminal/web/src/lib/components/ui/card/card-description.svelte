<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children }: Props = $props();
</script>

<p class={cn("text-sm text-muted-foreground", className)}>
  {#if children}
    {@render children()}
  {/if}
</p>
