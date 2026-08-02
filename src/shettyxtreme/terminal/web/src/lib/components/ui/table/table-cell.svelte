<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children }: Props = $props();
</script>

<td class={cn("px-2 py-1 align-middle whitespace-nowrap", className)}>
  {#if children}
    {@render children()}
  {/if}
</td>
