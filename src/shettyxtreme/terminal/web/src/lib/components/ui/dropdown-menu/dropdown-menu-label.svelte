<script lang="ts">
  import type { HTMLAttributes } from "svelte/elements";
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = HTMLAttributes<HTMLDivElement> & {
    class?: string;
    inset?: boolean;
    children?: Snippet;
  };

  const { class: className, inset, children, ...rest }: Props = $props();
</script>

<div
  class={cn("px-2.5 py-1.5 text-[11px] font-semibold tracking-[0.08em] text-muted-foreground uppercase", inset && "pl-8", className)}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</div>
