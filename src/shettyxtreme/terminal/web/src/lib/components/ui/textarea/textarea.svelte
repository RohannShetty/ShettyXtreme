<script lang="ts">
  import type { HTMLTextareaAttributes } from "svelte/elements";
  import { cn } from "$lib/utils.js";

  type Props = HTMLTextareaAttributes & {
    class?: string;
  };

  let { class: className, value = $bindable(""), ...rest }: Props = $props();
</script>

<textarea
  {value}
  class={cn(
    "flex min-h-16 w-full rounded-[4px] border border-hairline bg-canvas-raised px-2.5 py-1.5 text-[13px] text-ink transition-colors placeholder:text-faint hover:border-muted-foreground/60 focus-visible:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-default disabled:opacity-50",
    className
  )}
  {...rest}
></textarea>
