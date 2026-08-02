<script lang="ts">
  import type { HTMLThAttributes } from "svelte/elements";
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = HTMLThAttributes & { class?: string; children?: Snippet };

  const { class: className, children, ...rest }: Props = $props();
</script>

<th
  class={cn(
    "h-7 whitespace-nowrap px-2 py-1 text-left align-middle font-sans text-[10px] font-medium uppercase tracking-[0.08em] text-muted-foreground",
    className
  )}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</th>
