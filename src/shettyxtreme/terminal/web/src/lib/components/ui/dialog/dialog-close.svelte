<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";
  import { Dialog as DialogPrimitive } from "bits-ui";

  type Props = DialogPrimitive.CloseProps & { class?: string; children?: Snippet };

  const { class: className, children, ...rest }: Props = $props();
</script>

<DialogPrimitive.Close class={cn(className)} {...rest}>
  {#if children}
    {@render children()}
  {/if}
</DialogPrimitive.Close>
