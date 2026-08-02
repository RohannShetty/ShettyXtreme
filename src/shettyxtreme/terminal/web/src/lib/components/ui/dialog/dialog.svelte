<script lang="ts">
  import type { Snippet } from "svelte";
  import { Dialog as DialogPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = DialogPrimitive.RootProps & { children?: Snippet };

  const { children, ...rest }: Props = $props();
</script>

<DialogPrimitive.Root {...rest}>
  {#if children}
    {@render children()}
  {/if}
</DialogPrimitive.Root>
