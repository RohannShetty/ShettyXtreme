<script lang="ts">
  import type { Snippet } from "svelte";
  import { Select as SelectPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";
  import SelectPortal from "./select-portal.svelte";
  import SelectScrollDownButton from "./select-scroll-down-button.svelte";
  import SelectScrollUpButton from "./select-scroll-up-button.svelte";

  type Props = SelectPrimitive.ContentProps & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, sideOffset = 4, children, ...rest }: Props = $props();
</script>

<SelectPortal>
  <SelectPrimitive.Content
    {sideOffset}
    class={cn(
      "relative z-50 max-h-96 min-w-32 overflow-y-auto rounded-[4px] border border-hairline bg-surface-elevated p-1 text-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
      className
    )}
    {...rest}
  >
    <SelectScrollUpButton />
    <SelectPrimitive.Viewport class="w-full min-w-(--bits-select-anchor-width) scroll-my-1">
      {#if children}
        {@render children()}
      {/if}
    </SelectPrimitive.Viewport>
    <SelectScrollDownButton />
  </SelectPrimitive.Content>
</SelectPortal>
