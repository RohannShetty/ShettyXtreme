<script lang="ts">
  import type { HTMLAttributes } from "svelte/elements";
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";

  type Props = HTMLAttributes<HTMLSpanElement> & {
    class?: string;
    children?: Snippet;
  };

  const { class: className, children, ...rest }: Props = $props();
</script>

<span
  class={cn("ml-auto pl-2 font-mono text-[10px] tracking-widest text-faint", className)}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</span>
