<script lang="ts">
  import type { ResearchBrief } from "../lib/api";
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";

  let {
    brief,
    busy = false,
    onDecide = (_status: "approved" | "rejected") => {},
  }: {
    brief: ResearchBrief;
    busy?: boolean;
    onDecide?: (status: "approved" | "rejected") => void;
  } = $props();

  function dirBadgeClass(direction: number): string {
    return direction === 1 ? "price-up" : direction === -1 ? "price-down" : "dir-flat";
  }

  function dirLabel(direction: number): string {
    return direction === 1 ? "+1" : direction === -1 ? "−1" : "0";
  }

  function statusVariant(status: string): "success" | "danger" | "warning" {
    return status === "approved" ? "success" : status === "rejected" ? "danger" : "warning";
  }
</script>

<div class="detail">
  <div class="detail-head">
    <Badge variant="outline">{brief.lens}</Badge>
    <span class="num {dirBadgeClass(brief.direction)}">{dirLabel(brief.direction)}</span>
    <span class="conf mono">{(brief.confidence * 100).toFixed(0)}% confidence</span>
    <Badge variant={statusVariant(brief.status)}>{brief.status}</Badge>
  </div>
  <p class="thesis">{brief.thesis}</p>
  <p class="rationale">{brief.rationale}</p>
  <h4>Evidence</h4>
  <table class="evidence mono">
    <tbody>
      {#each brief.evidence as e (e.item + e.source)}
        <tr>
          <td>{e.item}</td>
          <td class="src">{e.unsourced ? "[UNSOURCED]" : e.source}</td>
        </tr>
      {/each}
    </tbody>
  </table>
  {#if brief.risks.length > 0}
    <h4>Risks</h4>
    <ul class="risks">
      {#each brief.risks as r (r)}
        <li>{r}</li>
      {/each}
    </ul>
  {/if}
  <div class="meta mono">
    <span>valid {brief.validity_window_minutes}m</span>
    <span>{brief.expired ? "expired" : "live"}</span>
    {#if brief.outcome}
      <span>outcome: {brief.outcome}</span>
    {/if}
    {#if brief.decided_at}
      <span>decided {brief.decided_at.slice(0, 19)}</span>
    {/if}
  </div>
  {#if brief.status === "proposed" && !brief.expired}
    <div class="decision">
      <Button variant="outline" class="flex-1 text-success border-success hover:border-success" onclick={() => onDecide("approved")} disabled={busy}>Approve</Button>
      <Button variant="danger" class="flex-1" onclick={() => onDecide("rejected")} disabled={busy}>Reject</Button>
    </div>
  {/if}
</div>

<style>
  .conf {
    color: var(--faint);
  }
  .dir-flat {
    color: var(--muted);
  }
  .detail-head {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 6px;
  }
  .thesis {
    white-space: normal;
    color: var(--ink);
    font-weight: 600;
    margin: 0 0 6px;
  }
  .rationale {
    color: var(--body);
    font-size: 11px;
    line-height: 1.5;
    margin: 0 0 8px;
  }
  h4 {
    margin: 8px 0 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.07em;
    color: var(--faint);
    text-transform: uppercase;
  }
  .evidence {
    width: 100%;
    border-collapse: collapse;
    font-size: 10px;
  }
  .evidence td {
    padding: 2px 4px;
    border-bottom: 1px solid var(--hairline);
    vertical-align: top;
  }
  .evidence .src {
    color: var(--faint);
  }
  .risks {
    list-style: disc;
    padding-left: 16px;
    font-size: 11px;
    color: var(--warning);
    margin: 0;
  }
  .meta {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    color: var(--faint);
    font-size: 10px;
    margin-top: 8px;
  }
  .decision {
    display: flex;
    gap: 8px;
    margin-top: 10px;
  }
</style>
