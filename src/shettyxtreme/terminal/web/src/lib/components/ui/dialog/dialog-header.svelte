<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = { class?: string; children?: Snippet };

  const { class: className, children }: Props = $props();
</script>

<div class={cn("flex flex-col space-y-1.5 text-left", className)}>
  {#if children}
    {@render children()}
  {/if}
</div>
