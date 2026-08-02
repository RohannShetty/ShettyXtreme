<script lang="ts">
  import type { HTMLTdAttributes } from "svelte/elements";
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = HTMLTdAttributes & { class?: string; children?: Snippet };

  const { class: className, children, ...rest }: Props = $props();
</script>

<td class={cn("px-2 py-1 align-middle whitespace-nowrap", className)} {...rest}>
  {#if children}
    {@render children()}
  {/if}
</td>
