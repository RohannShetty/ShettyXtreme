<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children }: Props = $props();
</script>

<tr
  class={cn(
    "border-b border-hairline transition-colors hover:bg-row-hover data-[state=selected]:border-l-2 data-[state=selected]:border-l-accent data-[state=selected]:bg-row-selected",
    className
  )}
>
  {#if children}
    {@render children()}
  {/if}
</tr>
