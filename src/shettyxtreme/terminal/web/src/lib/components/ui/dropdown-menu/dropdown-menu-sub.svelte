<script lang="ts">
  import type { Snippet } from "svelte";
  import { DropdownMenu as DropdownMenuPrimitive } from "bits-ui";

  type Props = DropdownMenuPrimitive.SubProps & { children?: Snippet };

  const { children, ...rest }: Props = $props();
</script>

<DropdownMenuPrimitive.Sub {...rest}>
  {#if children}
    {@render children()}
  {/if}
</DropdownMenuPrimitive.Sub>
