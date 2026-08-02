<script lang="ts">
  import type { HTMLInputAttributes } from "svelte/elements";
  import { cn } from "$lib/utils.js";

  type Props = HTMLInputAttributes & {
    class?: string;
  };

  let { class: className, value = $bindable(""), ...rest }: Props = $props();
</script>

<input
  {value}
  class={cn(
    "flex h-8 w-full rounded-[4px] border border-hairline bg-canvas-raised px-2.5 py-1 text-[13px] text-ink transition-colors placeholder:text-faint hover:border-muted-foreground/60 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-default disabled:bg-canvas disabled:text-faint",
    className
  )}
  {...rest}
/>
