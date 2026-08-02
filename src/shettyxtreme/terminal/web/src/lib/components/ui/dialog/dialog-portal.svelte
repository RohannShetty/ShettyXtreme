<script lang="ts">
  import type { Snippet } from "svelte";
  import { Dialog as DialogPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = DialogPrimitive.PortalProps & { children?: Snippet };

  const { children, ...rest }: Props = $props();
</script>

<DialogPrimitive.Portal {...rest}>
  {#if children}
    {@render children()}
  {/if}
</DialogPrimitive.Portal>
