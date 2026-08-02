<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";
  import { Dialog as DialogPrimitive } from "bits-ui";

  type Props = DialogPrimitive.TitleProps & { class?: string; children?: Snippet };

  const { class: className, children, ...rest }: Props = $props();
</script>

<DialogPrimitive.Title
  class={cn("font-sans text-sm font-semibold leading-none tracking-tight text-ink", className)}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</DialogPrimitive.Title>
