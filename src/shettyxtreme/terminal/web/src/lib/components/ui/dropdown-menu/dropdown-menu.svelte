<script lang="ts">
  import type { Snippet } from "svelte";
  import { DropdownMenu as DropdownMenuPrimitive } from "bits-ui";

  type Props = DropdownMenuPrimitive.RootProps & { children?: Snippet };

  const { children, ...rest }: Props = $props();
</script>

<DropdownMenuPrimitive.Root {...rest}>
  {#if children}
    {@render children()}
  {/if}
</DropdownMenuPrimitive.Root>
