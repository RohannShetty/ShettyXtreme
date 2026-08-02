<script lang="ts">
  import type { Snippet } from "svelte";
  import { Tabs as TabsPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = TabsPrimitive.ListProps & { class?: string; children?: Snippet };

  const { class: className, children, ...rest }: Props = $props();
</script>

<TabsPrimitive.List
  class={cn("inline-flex h-8 items-center border-b-2 border-hairline bg-canvas-raised text-muted-foreground", className)}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</TabsPrimitive.List>
