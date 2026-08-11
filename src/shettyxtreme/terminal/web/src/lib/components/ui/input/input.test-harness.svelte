<script lang="ts">
  import Input from "./input.svelte";

  let value = $state("");
</script>

<Input bind:value={value} aria-label="field" />
<p data-testid="bound">{value}</p>
