<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import {
    approveProposal,
    executionMode,
    getProposals,
    rejectProposal,
    riskSummary,
    type Proposal,
    type RiskSummary,
  } from "../lib/api";
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";
  import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
  } from "$lib/components/ui/dialog";
  import { RotateCw } from "@lucide/svelte";

  const POLL_MS = 5000;

  let proposals = $state<Proposal[]>([]);
  let mode = $state("OBSERVER");
  let risk: RiskSummary | null = $state(null);
  let error = $state("");
  let feedback = $state("");
  let target: Proposal | null = $state(null);
  let busy = $state(false);
  let timer: ReturnType<typeof setInterval> | undefined;

  onMount(() => {
    refresh();
    timer = setInterval(() => refresh(), POLL_MS);
  });

  onDestroy(() => {
    if (timer) clearInterval(timer);
  });

  async function refresh(): Promise<void> {
    try {
      const [p, m, r] = await Promise.all([
        getProposals(),
        executionMode(),
        riskSummary().catch(() => null),
      ]);
      proposals = p.filter((x) => x.status === "PENDING");
      mode = m.mode;
      risk = r;
      error = "";
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  function convictionLevel(conviction: number): string {
    if (conviction >= 0.75) return "EXTREME";
    if (conviction >= 0.5) return "HIGH";
    if (conviction >= 0.25) return "MEDIUM";
    return "LOW";
  }

  function convictionClass(level: string): string {
    switch (level) {
      case "EXTREME":
        return "border-hairline-strong bg-row-selected text-ink";
      case "HIGH":
        return "border-accent-disabled text-accent";
      case "MEDIUM":
        return "border-warning text-warning";
      default:
        return "border-hairline-strong text-muted-foreground";
    }
  }

  function timeStr(ts: string | null): string {
    if (!ts) return "—";
    const d = new Date(ts);
    return isNaN(d.getTime()) ? "—" : d.toLocaleTimeString("en-IN", { hour12: false });
  }

  function openConfirm(p: Proposal): void {
    feedback = "";
    target = p;
  }

  async function confirmApprove(): Promise<void> {
    const p = target;
    if (!p) return;
    busy = true;
    feedback = "";
    try {
      const updated = await approveProposal(p.id, mode === "LIVE");
      proposals = proposals.filter((x) => x.id !== p.id);
      feedback = `${updated.side} ${updated.symbol} → ${updated.status}`;
      target = null;
    } catch (err) {
      feedback = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
      refresh();
    }
  }

  async function doReject(p: Proposal): Promise<void> {
    feedback = "";
    try {
      await rejectProposal(p.id, "rejected by operator");
      proposals = proposals.filter((x) => x.id !== p.id);
      feedback = `${p.side} ${p.symbol} rejected`;
    } catch (err) {
      feedback = err instanceof Error ? err.message : String(err);
    }
  }

  function fmtMoney(v: number | null | undefined): string {
    if (v === null || v === undefined || !isFinite(v)) return "—";
    return v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
</script>

<section class="panel queue">
  <header class="panel-head">
    <div class="titles">
      <span class="eyebrow">EXECUTION</span>
      <h2>Proposal Queue</h2>
    </div>
    <div class="head-right">
      <span class="mode-chip" class:live={mode === "LIVE"}>{mode}</span>
      <Button
        variant="ghost"
        size="icon"
        class="size-7 text-muted-foreground hover:text-ink"
        onclick={() => refresh()}
        aria-label="Refresh proposals"
      >
        <RotateCw class="size-3.5" />
      </Button>
    </div>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {:else if proposals.length === 0}
    <p class="empty">
      No pending proposals.
      {#if mode === "OBSERVER"}
        Signals will queue here for approval — nothing is ever placed automatically.
      {/if}
    </p>
  {:else}
    <div class="rows">
      {#each proposals as p (p.id)}
        <div class="row">
          <div class="row-main">
            <div class="line1">
              <span class="sym mono">{p.symbol}</span>
              <Badge
                class={p.side === "BUY"
                  ? "border-price-up text-price-up"
                  : "border-price-down text-price-down"}
              >
                {p.side}
              </Badge>
              <Badge class={convictionClass(convictionLevel(p.conviction))}>
                {convictionLevel(p.conviction)}
              </Badge>
            </div>
            <div class="line2 mono">
              <span>QTY <b>{p.quantity}</b></span>
              <span>PRICE <b>{p.price != null ? fmtMoney(p.price) : "MKT"}</b></span>
              <span>TYPE <b>{p.order_type}</b></span>
              <span>{timeStr(p.timestamp)}</span>
            </div>
          </div>
          <div class="row-actions">
            <Button
              variant="default"
              size="sm"
              class="min-w-16"
              disabled={busy}
              onclick={() => openConfirm(p)}
            >
              APPROVE
            </Button>
            <Button
              variant="danger"
              size="sm"
              class="min-w-16"
              disabled={busy}
              onclick={() => doReject(p)}
            >
              REJECT
            </Button>
          </div>
        </div>
      {/each}
    </div>
  {/if}

  {#if feedback}
    <p class="feedback" class:bad={feedback.includes("-> REJECTED") || feedback.length > 60}>{feedback}</p>
  {/if}
</section>

<Dialog open={target !== null} onOpenChange={(o) => !o && (target = null)}>
  {#if target}
    <DialogContent>
      <DialogHeader>
        <DialogTitle>Confirm order</DialogTitle>
        <DialogDescription>
          Approving places this order in {mode} mode. Nothing is placed automatically.
        </DialogDescription>
      </DialogHeader>

      <div class="summary mono">
        <div class="sum-row"><span>SYMBOL</span><b>{target.symbol}</b></div>
        <div class="sum-row"><span>SIDE</span><b class={target.side === "BUY" ? "up" : "down"}>{target.side}</b></div>
        <div class="sum-row"><span>QUANTITY</span><b>{target.quantity}</b></div>
        <div class="sum-row"><span>PRICE</span><b>{target.price != null ? fmtMoney(target.price) : "MARKET"}</b></div>
        <div class="sum-row"><span>ORDER TYPE</span><b>{target.order_type}</b></div>
        <div class="sum-row"><span>PRODUCT</span><b>{target.product}</b></div>
      </div>

      {#if risk}
        <div class="summary mono risk">
          <div class="sum-row"><span>DAILY P&L</span><b class={risk.daily_pnl >= 0 ? "up" : "down"}>{fmtMoney(risk.daily_pnl)}</b></div>
          <div class="sum-row"><span>MARGIN AVAIL</span><b>{fmtMoney(risk.margin_available)}</b></div>
          <div class="sum-row"><span>LOSS LIMIT</span><b>{fmtMoney(risk.loss_limit)}</b></div>
          <div class="sum-row"><span>ACTIVE POS</span><b>{risk.active_positions}/{risk.max_positions}</b></div>
        </div>
      {/if}

      <DialogFooter>
        <Button variant="ghost" onclick={() => (target = null)} disabled={busy}>Cancel</Button>
        <Button variant="default" onclick={confirmApprove} disabled={busy}>
          Confirm {target.side} {target.quantity} {target.symbol}
        </Button>
      </DialogFooter>
    </DialogContent>
  {/if}
</Dialog>

<style>
  .queue {
    display: flex;
    flex-direction: column;
    min-width: 320px;
    min-height: 0;
    max-height: 420px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-radius: 6px;
  }
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
  }
  .titles {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .eyebrow {
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--faint);
  }
  .panel-head h2 {
    margin: 0;
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
  }
  .head-right {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .mode-chip {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--muted);
    border: 1px solid var(--hairline-strong);
    border-radius: 4px;
    padding: 2px 6px;
  }
  .mode-chip.live {
    color: var(--accent);
    border-color: var(--accent);
  }
  .rows {
    overflow-y: auto;
    display: flex;
    flex-direction: column;
  }
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
  }
  .row:hover {
    background: var(--row-hover);
  }
  .row-main {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }
  .line1 {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .sym {
    color: var(--ink);
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.02em;
  }
  .line2 {
    display: flex;
    gap: 12px;
    font-size: 11px;
    color: var(--muted);
    white-space: nowrap;
  }
  .line2 b {
    color: var(--ink);
    font-weight: 500;
    margin-left: 3px;
  }
  .row-actions {
    display: flex;
    gap: 6px;
    flex: none;
  }
  .empty {
    color: var(--faint);
    font-size: 12px;
    padding: 16px 10px;
    margin: 0;
    line-height: 1.6;
  }
  .error {
    color: var(--danger);
    font-size: 11px;
    padding: 8px 10px;
    margin: 0;
  }
  .feedback {
    margin: 0;
    padding: 6px 10px;
    border-top: 1px solid var(--hairline);
    color: var(--success);
    font-size: 11px;
  }
  .feedback.bad {
    color: var(--danger);
  }
  .summary {
    display: flex;
    flex-direction: column;
    gap: 4px;
    background: var(--canvas-raised);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    padding: 10px 12px;
    font-size: 12px;
  }
  .summary.risk {
    background: var(--surface-elevated);
    border-color: var(--hairline-strong);
  }
  .sum-row {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
  }
  .sum-row span {
    color: var(--muted);
    font-size: 10px;
    letter-spacing: 0.08em;
  }
  .sum-row b {
    color: var(--ink);
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }
  .sum-row b.up {
    color: var(--price-up);
  }
  .sum-row b.down {
    color: var(--price-down);
  }
  .mono {
    font-family: "JetBrains Mono", "IBM Plex Mono", ui-monospace, monospace;
    font-variant-numeric: tabular-nums;
  }
</style>
