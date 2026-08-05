<script lang="ts">
  import TableRow from "./table-row.svelte";

  let keyCount = $state(0);
</script>

<TableRow
  data-state="selected"
  aria-selected="true"
  data-testid="row"
  onkeydown={() => (keyCount += 1)}
>
  <td>cell</td>
</TableRow>
<p data-testid="keys">{keyCount}</p>
