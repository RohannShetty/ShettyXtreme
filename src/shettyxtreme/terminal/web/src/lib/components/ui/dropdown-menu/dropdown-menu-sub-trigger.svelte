<script lang="ts">
  import type { Snippet } from "svelte";
  import { DropdownMenu as DropdownMenuPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";
  import { ChevronRight } from "@lucide/svelte";

  type Props = DropdownMenuPrimitive.SubTriggerProps & {
    class?: string;
    inset?: boolean;
    children?: Snippet;
  };

  const { class: className, inset, children, ...rest }: Props = $props();
</script>

<DropdownMenuPrimitive.SubTrigger
  class={cn(
    "flex cursor-default select-none items-center gap-2 rounded-[2px] px-2.5 py-2 text-[13px] text-body outline-none transition-colors data-highlighted:bg-row-hover data-highlighted:text-ink data-disabled:pointer-events-none data-disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg]:size-4",
    inset && "pl-8",
    className
  )}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
  <ChevronRight class="ml-auto text-muted-foreground" />
</DropdownMenuPrimitive.SubTrigger>
