<script lang="ts">
  import { cn } from "$lib/utils.js";
  import { Check } from "@lucide/svelte";

  const { class: className }: { class?: string } = $props();
</script>

<Check class={cn("size-3.5", className)} />
