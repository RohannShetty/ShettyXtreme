<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = { class?: string; children?: Snippet };

  const { class: className, children }: Props = $props();
</script>

<div class={cn("flex flex-col-reverse sm:flex-row sm:justify-end sm:gap-2", className)}>
  {#if children}
    {@render children()}
  {/if}
</div>
