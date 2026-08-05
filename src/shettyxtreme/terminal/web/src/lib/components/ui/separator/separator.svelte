<script lang="ts">
  import type { Snippet } from "svelte";
  import { Separator as SeparatorPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = SeparatorPrimitive.RootProps & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children, ...rest }: Props = $props();
</script>

<SeparatorPrimitive.Root
  class={cn(
    "shrink-0 bg-hairline-strong data-[orientation=horizontal]:h-px data-[orientation=horizontal]:w-full data-[orientation=vertical]:h-full data-[orientation=vertical]:w-px",
    className
  )}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</SeparatorPrimitive.Root>
