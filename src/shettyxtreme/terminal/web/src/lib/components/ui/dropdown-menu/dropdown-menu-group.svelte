<script lang="ts">
  import type { Snippet } from "svelte";
  import { DropdownMenu as DropdownMenuPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = DropdownMenuPrimitive.GroupProps & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children, ...rest }: Props = $props();
</script>

<DropdownMenuPrimitive.Group class={cn("", className)} {...rest}>
  {#if children}
    {@render children()}
  {/if}
</DropdownMenuPrimitive.Group>
