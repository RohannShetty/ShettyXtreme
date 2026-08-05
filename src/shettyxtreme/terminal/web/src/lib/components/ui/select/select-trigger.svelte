<script lang="ts">
  import type { Snippet } from "svelte";
  import { Select as SelectPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";
  import { ChevronDown } from "@lucide/svelte";

  type Props = SelectPrimitive.TriggerProps & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children, ...rest }: Props = $props();
</script>

<SelectPrimitive.Trigger
  class={cn(
    "flex h-8 w-full items-center justify-between gap-2 whitespace-nowrap rounded-[4px] border border-hairline bg-canvas-raised px-2.5 py-1 text-[13px] text-ink transition-colors focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-default disabled:opacity-50 [&>span]:line-clamp-1 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg]:size-3.5 [&_svg]:text-muted-foreground",
    className
  )}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
  <ChevronDown />
</SelectPrimitive.Trigger>
