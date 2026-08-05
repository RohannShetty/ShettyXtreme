<script lang="ts">
  import type { Snippet } from "svelte";
  import { Select as SelectPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";
  import { ChevronUp } from "@lucide/svelte";

  type Props = SelectPrimitive.ScrollUpButtonProps & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children, ...rest }: Props = $props();
</script>

<SelectPrimitive.ScrollUpButton
  class={cn("top-0 flex w-full cursor-default items-center justify-center py-1 text-muted-foreground", className)}
  {...rest}
>
  {#if children}
    {@render children()}
  {:else}
    <ChevronUp class="size-3.5" />
  {/if}
</SelectPrimitive.ScrollUpButton>
