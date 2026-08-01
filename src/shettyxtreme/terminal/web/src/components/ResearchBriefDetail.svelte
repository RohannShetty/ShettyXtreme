<script lang="ts">
  import type { ResearchBrief } from "../lib/api";

  export let brief: ResearchBrief;
  export let busy = false;
  export let onDecide: (status: "approved" | "rejected") => void = () => {};

  function dirBadgeClass(direction: number): string {
    return direction === 1 ? "price-up" : direction === -1 ? "price-down" : "dir-flat";
  }

  function dirLabel(direction: number): string {
    return direction === 1 ? "+1" : direction === -1 ? "−1" : "0";
  }

  function statusClass(status: string): string {
    return status === "approved" ? "ok" : status === "rejected" ? "bad" : "pending";
  }
</script>

<div class="detail">
  <div class="detail-head">
    <span class="tag">{brief.lens}</span>
    <span class="num {dirBadgeClass(brief.direction)}">{dirLabel(brief.direction)}</span>
    <span class="conf mono">{(brief.confidence * 100).toFixed(0)}% confidence</span>
    <span class="tag {statusClass(brief.status)}">{brief.status}</span>
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
      <button class="approve" on:click={() => onDecide("approved")} disabled={busy}>Approve</button>
      <button class="reject" on:click={() => onDecide("rejected")} disabled={busy}>Reject</button>
    </div>
  {/if}
</div>

<style>
  .tag {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    border: 1px solid var(--hairline-strong);
    border-radius: 4px;
    padding: 1px 5px;
    white-space: nowrap;
  }
  .tag.ok {
    color: var(--success);
    border-color: var(--success);
  }
  .tag.bad {
    color: var(--danger);
    border-color: var(--danger);
  }
  .tag.pending {
    color: var(--warning);
    border-color: var(--warning);
  }
  .dir-flat {
    color: var(--muted);
  }
  .conf {
    color: var(--faint);
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
  .decision button {
    flex: 1;
    border-radius: 4px;
    border: 1px solid var(--hairline-strong);
    background: none;
    padding: 5px 0;
    font-size: 11px;
    cursor: pointer;
  }
  .decision button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .approve {
    color: var(--success);
    border-color: var(--success) !important;
  }
  .reject {
    color: var(--danger);
    border-color: var(--danger) !important;
  }
</style>
