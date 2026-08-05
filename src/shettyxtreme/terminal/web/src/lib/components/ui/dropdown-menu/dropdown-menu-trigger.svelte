<script lang="ts">
  import type { Snippet } from "svelte";
  import { DropdownMenu as DropdownMenuPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = DropdownMenuPrimitive.TriggerProps & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children, ...rest }: Props = $props();
</script>

<DropdownMenuPrimitive.Trigger
  class={cn("flex cursor-default items-center outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2", className)}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</DropdownMenuPrimitive.Trigger>
