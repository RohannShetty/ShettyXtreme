<script lang="ts">
  import { DropdownMenu as DropdownMenuPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = DropdownMenuPrimitive.SeparatorProps & {
    class?: string;
  };

  const { class: className, ...rest }: Props = $props();
</script>

<DropdownMenuPrimitive.Separator
  class={cn("-mx-1 my-1 h-px bg-hairline", className)}
  {...rest}
/>
