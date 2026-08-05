<script lang="ts">
  import type { Snippet } from "svelte";
  import { ScrollArea as ScrollAreaPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";
  import Scrollbar from "./scroll-area-scrollbar.svelte";

  type Props = ScrollAreaPrimitive.RootProps & {
    class?: string;
    /** Which scrollbars to render. "vertical" (default) / "horizontal" / "both". */
    orientation?: "vertical" | "horizontal" | "both";
    /** Extra classes for the horizontal scrollbar (when orientation is both). */
    scrollbarXClasses?: string;
    /** Extra classes for the vertical scrollbar. */
    scrollbarYClasses?: string;
    children?: Snippet;
  };

  const {
    class: className,
    orientation = "vertical",
    scrollbarXClasses = "",
    scrollbarYClasses = "",
    children,
    ...rest
  }: Props = $props();
</script>

<ScrollAreaPrimitive.Root class={cn("relative overflow-hidden", className)} {...rest}>
  <ScrollAreaPrimitive.Viewport
    class="size-full rounded-[inherit] outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
  >
    {#if children}
      {@render children()}
    {/if}
  </ScrollAreaPrimitive.Viewport>
  {#if orientation === "vertical" || orientation === "both"}
    <Scrollbar orientation="vertical" class={scrollbarYClasses} />
  {/if}
  {#if orientation === "horizontal" || orientation === "both"}
    <Scrollbar orientation="horizontal" class={scrollbarXClasses} />
  {/if}
  <ScrollAreaPrimitive.Corner class="bg-surface-elevated" />
</ScrollAreaPrimitive.Root>
