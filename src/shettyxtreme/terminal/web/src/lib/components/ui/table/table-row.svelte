<script lang="ts">
  import type { HTMLAttributes } from "svelte/elements";
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = HTMLAttributes<HTMLTableRowElement> & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children, ...rest }: Props = $props();
</script>

<tr
  class={cn(
    "border-b border-hairline transition-colors hover:bg-row-hover data-[state=selected]:border-l-2 data-[state=selected]:border-l-accent data-[state=selected]:bg-row-selected",
    className
  )}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</tr>
