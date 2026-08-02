<script lang="ts">
  import type { Snippet } from "svelte";
  import { Dialog as DialogPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = DialogPrimitive.OverlayProps & { class?: string; children?: Snippet };

  const { class: className, children, ...rest }: Props = $props();
</script>

<DialogPrimitive.Overlay
  class={cn("fixed inset-0 z-40 bg-scrim", className)}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</DialogPrimitive.Overlay>
