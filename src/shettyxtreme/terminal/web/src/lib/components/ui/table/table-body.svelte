<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children }: Props = $props();
</script>

<tbody class={cn("[&_tr:last-child]:border-0", className)}>
  {#if children}
    {@render children()}
  {/if}
</tbody>
