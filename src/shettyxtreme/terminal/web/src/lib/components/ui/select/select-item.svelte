<script lang="ts">
  import type { Snippet } from "svelte";
  import { Select as SelectPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";
  import { Check } from "@lucide/svelte";

  type Props = SelectPrimitive.ItemProps & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children: childrenProp, value, label, ...rest }: Props = $props();
</script>

<SelectPrimitive.Item
  {value}
  {label}
  class={cn(
    "relative flex w-full cursor-default select-none items-center rounded-[2px] py-2 pr-8 pl-2.5 text-[13px] text-body outline-none transition-colors data-highlighted:bg-row-hover data-highlighted:text-ink data-disabled:pointer-events-none data-disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg]:size-4",
    className
  )}
  {...rest}
>
  {#snippet children({ selected })}
    <span class="absolute right-2 flex size-3.5 items-center justify-center">
      {#if selected}
        <Check class="size-3.5 text-accent" />
      {/if}
    </span>
    {#if childrenProp}
      {@render childrenProp()}
    {:else}
      {label ?? value}
    {/if}
  {/snippet}
</SelectPrimitive.Item>
