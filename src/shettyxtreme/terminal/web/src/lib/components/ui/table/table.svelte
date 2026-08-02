<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children }: Props = $props();
</script>

<div class={cn("relative w-full overflow-auto", className)}>
  <table class="w-full caption-bottom border-collapse text-[12px]">
    {#if children}
      {@render children()}
    {/if}
  </table>
</div>
