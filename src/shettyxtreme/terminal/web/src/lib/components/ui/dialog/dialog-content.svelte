<script lang="ts">
  import type { Snippet } from "svelte";
  import { Dialog as DialogPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = DialogPrimitive.ContentProps & {
    class?: string;
    overlay?: Snippet;
    children?: Snippet;
  };

  const { class: className, overlay, children, ...rest }: Props = $props();
</script>

<DialogPrimitive.Portal>
  <DialogPrimitive.Overlay
    class="fixed inset-0 z-40 bg-scrim duration-[120ms] data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0"
  >
    {#if overlay}
      {@render overlay()}
    {/if}
  </DialogPrimitive.Overlay>
  <DialogPrimitive.Content
    class={cn(
      "fixed left-1/2 top-1/2 z-50 grid w-[min(420px,90vw)] -translate-x-1/2 -translate-y-1/2 gap-4 rounded-[6px] border border-hairline-strong bg-surface-overlay p-4 text-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 duration-[120ms] data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95",
      className
    )}
    {...rest}
  >
    {#if children}
      {@render children()}
    {/if}
  </DialogPrimitive.Content>
</DialogPrimitive.Portal>
