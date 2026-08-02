<script lang="ts">
  import type { Snippet } from "svelte";
  import { Tooltip as TooltipPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = TooltipPrimitive.ProviderProps & { children?: Snippet };

  const { children, ...rest }: Props = $props();
</script>

<TooltipPrimitive.Provider delayDuration={400} {...rest}>
  {#if children}
    {@render children()}
  {/if}
</TooltipPrimitive.Provider>
