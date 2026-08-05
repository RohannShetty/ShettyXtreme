<script lang="ts">
  import type { HTMLAttributes } from "svelte/elements";
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = HTMLAttributes<HTMLElement> & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children, ...rest }: Props = $props();
</script>

<kbd
  class={cn(
    "pointer-events-none inline-flex h-5 items-center gap-1 rounded-[2px] border border-hairline bg-surface-elevated px-1.5 font-mono text-[10px] font-medium text-muted-foreground select-none",
    className
  )}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</kbd>
