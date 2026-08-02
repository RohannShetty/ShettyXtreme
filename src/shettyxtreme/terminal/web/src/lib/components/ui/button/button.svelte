<script lang="ts">
  import type { HTMLButtonAttributes } from "svelte/elements";
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";
  import { buttonVariants, type ButtonVariant, type ButtonSize } from "./index.js";

  type Props = HTMLButtonAttributes & {
    class?: string;
    variant?: ButtonVariant;
    size?: ButtonSize;
    children?: Snippet;
  };

  const {
    class: className,
    variant = "default",
    size = "default",
    children,
    ...rest
  }: Props = $props();
</script>

<button
  data-slot="button"
  class={cn(buttonVariants({ variant, size }), className)}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</button>
