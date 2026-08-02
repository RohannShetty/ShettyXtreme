<script lang="ts">
  import type { Snippet } from "svelte";
  import { Tabs as TabsPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = TabsPrimitive.TriggerProps & { class?: string; children?: Snippet };

  const { class: className, children, ...rest }: Props = $props();
</script>

<TabsPrimitive.Trigger
  class={cn(
    "inline-flex h-8 items-center justify-center gap-1.5 border-b-2 border-transparent px-3 font-sans text-[11px] font-semibold tracking-[0.06em] text-muted-foreground transition-colors whitespace-nowrap hover:text-body focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:text-faint data-[state=active]:border-accent data-[state=active]:text-ink",
    className
  )}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</TabsPrimitive.Trigger>
