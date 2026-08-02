<script lang="ts">
  import type { Snippet } from "svelte";
  import { Dialog as DialogPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = DialogPrimitive.TriggerProps & { class?: string; children?: Snippet };

  const { class: className, children, ...rest }: Props = $props();
</script>

<DialogPrimitive.Trigger class={cn(className)} {...rest}>
  {#if children}
    {@render children()}
  {/if}
</DialogPrimitive.Trigger>
