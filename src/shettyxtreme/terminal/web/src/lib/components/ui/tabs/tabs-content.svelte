<script lang="ts">
  import type { Snippet } from "svelte";
  import { Tabs as TabsPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = TabsPrimitive.ContentProps & { class?: string; children?: Snippet };

  const { class: className, children, ...rest }: Props = $props();
</script>

<TabsPrimitive.Content class={cn("min-h-0 flex-1 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2", className)} {...rest}>
  {#if children}
    {@render children()}
  {/if}
</TabsPrimitive.Content>
