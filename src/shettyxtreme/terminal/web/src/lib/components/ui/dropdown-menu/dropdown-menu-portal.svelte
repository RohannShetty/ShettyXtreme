<script lang="ts">
  import type { ComponentProps } from "svelte";
  import { DropdownMenu as DropdownMenuPrimitive } from "bits-ui";

  type Props = ComponentProps<typeof DropdownMenuPrimitive.Portal>;

  const { ...rest }: Props = $props();
</script>

<DropdownMenuPrimitive.Portal {...rest} />
