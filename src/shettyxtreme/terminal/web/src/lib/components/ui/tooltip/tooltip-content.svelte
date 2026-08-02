<script lang="ts">
  import type { Snippet } from "svelte";
  import { Tooltip as TooltipPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = TooltipPrimitive.ContentProps & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children, ...rest }: Props = $props();
</script>

<TooltipPrimitive.Portal>
  <TooltipPrimitive.Content
    class={cn(
      "z-50 rounded-[6px] border border-hairline bg-surface-overlay px-2 py-1 font-sans text-[12px] leading-4 text-ink shadow-none select-none",
      className
    )}
    {...rest}
  >
    {#if children}
      {@render children()}
    {/if}
  </TooltipPrimitive.Content>
</TooltipPrimitive.Portal>
