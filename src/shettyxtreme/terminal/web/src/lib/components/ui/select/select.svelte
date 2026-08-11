<script lang="ts">
  import type { Snippet } from "svelte";
  import { Select as SelectPrimitive } from "bits-ui";

  type Props = SelectPrimitive.RootProps & { children?: Snippet };

  const { children, ...rest }: Props = $props();
</script>

<SelectPrimitive.Root {...rest}>
  {#if children}
    {@render children()}
  {/if}
</SelectPrimitive.Root>
