<script lang="ts">
  import type { HTMLAttributes } from "svelte/elements";
  import { cn } from "$lib/utils.js";

  type Props = HTMLAttributes<HTMLDivElement> & {
    class?: string;
  };

  const { class: className, ...rest }: Props = $props();
</script>

<div
  data-slot="skeleton"
  class={cn("animate-pulse rounded-[4px] bg-surface-elevated", className)}
  {...rest}
></div>
