<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";
  import { badgeVariants, type BadgeVariant } from "./index.js";

  type Props = {
    class?: string;
    variant?: BadgeVariant;
    children?: Snippet;
  };

  const { class: className, variant = "default", children }: Props = $props();
</script>

<span class={cn(badgeVariants({ variant }), className)}>
  {#if children}
    {@render children()}
  {/if}
</span>
