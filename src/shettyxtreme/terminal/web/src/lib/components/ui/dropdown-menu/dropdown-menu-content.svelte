<script lang="ts">
  import type { Snippet } from "svelte";
  import { DropdownMenu as DropdownMenuPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";
  import DropdownMenuPortal from "./dropdown-menu-portal.svelte";

  type Props = DropdownMenuPrimitive.ContentProps & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, sideOffset = 4, align = "start", children, ...rest }: Props = $props();
</script>

<DropdownMenuPortal>
  <DropdownMenuPrimitive.Content
    {sideOffset}
    {align}
    class={cn(
      "z-50 min-w-32 overflow-hidden rounded-[4px] border border-hairline bg-surface-elevated p-1 text-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
      className
    )}
    {...rest}
  >
    {#if children}
      {@render children()}
    {/if}
  </DropdownMenuPrimitive.Content>
</DropdownMenuPortal>
