<script lang="ts">
  import type { Snippet } from "svelte";
  import { Tabs as TabsPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = TabsPrimitive.RootProps & { class?: string; children?: Snippet };

  const { class: className, children, ...rest }: Props = $props();
</script>

<TabsPrimitive.Root class={cn(className)} {...rest}>
  {#if children}
    {@render children()}
  {/if}
</TabsPrimitive.Root>
