<script lang="ts">
  import Textarea from "./textarea.svelte";

  let value = $state("");
</script>

<Textarea bind:value={value} aria-label="field" />
<p data-testid="bound">{value}</p>
