<script lang="ts">
  import type { Snippet } from "svelte";
  import { Select as SelectPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = SelectPrimitive.GroupProps & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children, ...rest }: Props = $props();
</script>

<SelectPrimitive.Group class={cn("", className)} {...rest}>
  {#if children}
    {@render children()}
  {/if}
</SelectPrimitive.Group>
