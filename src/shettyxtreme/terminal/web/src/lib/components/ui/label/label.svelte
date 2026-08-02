<script lang="ts">
  import type { HTMLAttributes } from "svelte/elements";
  import { cn } from "$lib/utils.js";

  type Props = HTMLAttributes<HTMLLabelElement> & { class?: string };

  const { class: className, ...rest }: Props = $props();
</script>

<label
  class={cn(
    "inline-flex select-none items-center gap-2 text-[13px] leading-none text-body peer-disabled:cursor-default peer-disabled:opacity-50",
    className
  )}
  {...rest}
></label>
