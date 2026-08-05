<script lang="ts">
  import type { Snippet } from "svelte";
  import { Select as SelectPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = SelectPrimitive.GroupHeadingProps & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children, ...rest }: Props = $props();
</script>

<SelectPrimitive.GroupHeading
  class={cn("px-2.5 py-1.5 text-[11px] font-semibold tracking-[0.08em] text-muted-foreground uppercase", className)}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</SelectPrimitive.GroupHeading>
