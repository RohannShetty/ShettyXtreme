<script lang="ts">
  import type { Snippet } from "svelte";
  import { Tooltip as TooltipPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = TooltipPrimitive.TriggerProps & { class?: string; children?: Snippet };

  const { class: className, children, ...rest }: Props = $props();
</script>

<TooltipPrimitive.Trigger class={cn("inline-flex", className)} {...rest}>
  {#if children}
    {@render children()}
  {/if}
</TooltipPrimitive.Trigger>
