<script lang="ts">
  import { Separator as SeparatorPrimitive } from "bits-ui";
  import { cn } from "$lib/utils.js";

  type Props = SeparatorPrimitive.RootProps & {
    class?: string;
  };

  const { class: className, ...rest }: Props = $props();
</script>

<SeparatorPrimitive.Root
  class={cn("-mx-1 my-1 h-px bg-hairline", className)}
  {...rest}
/>
