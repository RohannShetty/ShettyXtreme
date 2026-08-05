<script lang="ts">
  import type { Snippet } from "svelte";
  import { DropdownMenu as DropdownMenuPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";
  import { Check } from "@lucide/svelte";

  type Props = DropdownMenuPrimitive.RadioItemProps & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children: childrenProp, ...rest }: Props = $props();
</script>

<DropdownMenuPrimitive.RadioItem
  class={cn(
    "relative flex cursor-default select-none items-center gap-2 rounded-[2px] py-2 pr-2.5 pl-8 text-[13px] text-body outline-none transition-colors data-highlighted:bg-row-hover data-highlighted:text-ink data-disabled:pointer-events-none data-disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg]:size-4",
    className
  )}
  {...rest}
>
  {#snippet children({ checked })}
    <span class="absolute left-2 flex size-4 items-center justify-center text-ink">
      {#if checked}
        <Check class="size-3.5" />
      {/if}
    </span>
    {#if childrenProp}
      {@render childrenProp()}
    {/if}
  {/snippet}
</DropdownMenuPrimitive.RadioItem>
