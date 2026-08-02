<script lang="ts">
  import type { Snippet } from "svelte";
  import { cn } from "$lib/utils.js";
  import { Dialog as DialogPrimitive } from "bits-ui";

  type Props = DialogPrimitive.DescriptionProps & { class?: string; children?: Snippet };

  const { class: className, children, ...rest }: Props = $props();
</script>

<DialogPrimitive.Description
  class={cn("text-[12px] leading-relaxed text-muted-foreground", className)}
  {...rest}
>
  {#if children}
    {@render children()}
  {/if}
</DialogPrimitive.Description>
