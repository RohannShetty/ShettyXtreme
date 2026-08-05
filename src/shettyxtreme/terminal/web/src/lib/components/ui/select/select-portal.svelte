<script lang="ts">
  import type { ComponentProps } from "svelte";
  import { Select as SelectPrimitive } from "bits-ui";

  type Props = ComponentProps<typeof SelectPrimitive.Portal>;

  const { ...rest }: Props = $props();
</script>

<SelectPrimitive.Portal {...rest} />
