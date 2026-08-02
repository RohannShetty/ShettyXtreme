<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";
  import { Checkbox as CheckboxPrimitive } from "bits-ui";

  type Props = {
    class?: string;
    checked?: boolean;
    disabled?: boolean;
    required?: boolean;
    onCheckedChange?: (checked: boolean) => void;
    children?: Snippet;
  };

  const {
    class: className,
    checked,
    disabled = false,
    required = false,
    onCheckedChange,
    children,
  }: Props = $props();
</script>

<CheckboxPrimitive.Root
  {disabled}
  {required}
  {checked}
  {onCheckedChange}
  class={cn(
    "peer flex size-4 shrink-0 items-center justify-center rounded-[4px] border border-hairline-strong bg-canvas-raised text-on-accent transition-colors hover:border-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background data-[state=checked]:border-accent data-[state=checked]:bg-accent disabled:cursor-default disabled:opacity-50",
    className
  )}
>
  {#if children}
    {@render children()}
  {/if}
</CheckboxPrimitive.Root>
