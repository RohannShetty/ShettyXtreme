<script lang="ts">
  import type { Snippet } from "svelte";
  import { ScrollArea as ScrollAreaPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = ScrollAreaPrimitive.ScrollbarProps & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, orientation, children, ...rest }: Props = $props();
</script>

<ScrollAreaPrimitive.Scrollbar
  {orientation}
  class={cn(
    "flex touch-none p-px transition-colors select-none",
    orientation === "vertical" && "h-full w-2.5 border-l border-l-transparent",
    orientation === "horizontal" && "h-2.5 flex-col border-t border-t-transparent",
    className
  )}
  {...rest}
>
  <ScrollAreaPrimitive.Thumb
    class="relative flex-1 rounded-[5px] bg-hairline-strong hover:bg-muted"
  />
  {#if children}
    {@render children()}
  {/if}
</ScrollAreaPrimitive.Scrollbar>
