<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children }: Props = $props();
</script>

<h3 class={cn("font-sans text-sm font-semibold leading-none text-ink", className)}>
  {#if children}
    {@render children()}
  {/if}
</h3>
