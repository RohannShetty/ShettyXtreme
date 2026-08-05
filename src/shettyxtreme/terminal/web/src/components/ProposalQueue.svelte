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
  import { Badge, type BadgeVariant } from "$lib/components/ui/badge";
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
  // Matches the backend staleness threshold (STALENESS_THRESHOLD_SEC = 30.0);
  // proposals older than this get a warning STALE chip (DESIGN §4).
  const STALE_MS = 30_000;

  let proposals = $state<Proposal[]>([]);
  let mode = $state("OBSERVER");
  let csrfToken = $state<string | null>(null);
  let risk: RiskSummary | null = $state(null);
  let error = $state("");
  let feedback = $state("");
  let target: Proposal | null = $state(null);
  let busy = $state(false);
  let now = $state(Date.now());
  let timer: ReturnType<typeof setInterval> | undefined;
  let nowTimer: ReturnType<typeof setInterval> | undefined;

  let isLive = $derived(mode === "LIVE");
  // The backend refuses approvals in OBSERVER ("OBSERVER mode never places
  // orders"). Disable APPROVE there instead of surfacing a failed call.
  let canApprove = $derived(mode !== "OBSERVER");

  onMount(() => {
    refresh();
    timer = setInterval(() => refresh(), POLL_MS);
    nowTimer = setInterval(() => (now = Date.now()), 1000);
    window.addEventListener("keydown", onWindowKey);
  });

  onDestroy(() => {
    if (timer) clearInterval(timer);
    if (nowTimer) clearInterval(nowTimer);
    window.removeEventListener("keydown", onWindowKey);
  });

  // Keyboard: Enter approves the open confirm dialog (Esc closes it — the
  // dialog primitive handles Escape → onOpenChange(false)).
  function onWindowKey(event: KeyboardEvent): void {
    if (target === null || event.key !== "Enter") return;
    event.preventDefault();
    if (!busy) void confirmApprove();
  }

  async function refresh(): Promise<void> {
    try {
      const [p, m, r] = await Promise.all([
        getProposals(),
        executionMode(),
        riskSummary().catch(() => null),
      ]);
      proposals = p.filter((x) => x.status === "PENDING");
      mode = m.mode;
      csrfToken = m.csrf_token;
      risk = r;
      error = "";
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  // DESIGN §4 "Badge — conviction" 4-level scale: EXTREME ≥0.75, HIGH ≥0.5,
  // MEDIUM ≥0.25, else LOW. Rendered via the badge primitive's conviction-*
  // variants (no ad-hoc Tailwind on the component).
  function convictionVariant(conviction: number): BadgeVariant {
    if (conviction >= 0.75) return "conviction-extreme";
    if (conviction >= 0.5) return "conviction-high";
    if (conviction >= 0.25) return "conviction-medium";
    return "conviction-low";
  }

  function convictionLabel(level: BadgeVariant): string {
    return level.slice("conviction-".length).toUpperCase();
  }

  function timeStr(ts: string | null): string {
    if (!ts) return "—";
    const d = new Date(ts);
    return isNaN(d.getTime()) ? "—" : d.toLocaleTimeString("en-IN", { hour12: false });
  }

  function isStale(ts: string | null): boolean {
    if (!ts) return false;
    const t = new Date(ts).getTime();
    return !isNaN(t) && now - t > STALE_MS;
  }

  function ageSeconds(ts: string | null): number | null {
    if (!ts) return null;
    const t = new Date(ts).getTime();
    return isNaN(t) ? null : Math.max(0, Math.floor((now - t) / 1000));
  }

  function modeChipClass(): string {
    switch (mode) {
      case "LIVE":
        return "chip-live";
      case "PAPER":
        return "chip-paper";
      default:
        return "chip-observer";
    }
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
      // LIVE placements require the per-session CSRF token minted by typed
      // LIVE activation + explicit confirm=true (verified against the backend
      // contract in execution_router.approve_proposal).
      const updated = await approveProposal(p.id, isLive, isLive ? csrfToken : null);
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

  // Indian grouping for all monetary values (en-IN lakh/crore), DESIGN §7.
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
      <span class="mode-chip {modeChipClass()}">
        {#if isLive}<span class="chip-dot" aria-hidden="true"></span>{/if}
        {mode}
      </span>
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

  {#if mode === "OBSERVER"}
    <p class="observer-note">
      OBSERVER — proposals only. Nothing is placed automatically; switch to PAPER or LIVE to
      execute.
    </p>
  {/if}

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
        {@const stale = isStale(p.timestamp)}
        {@const conv = convictionVariant(p.conviction)}
        <div
          class="row"
          tabindex="0"
          role="button"
          aria-label={`${p.symbol} ${p.side} ${p.quantity} — press Enter to review and approve`}
          onkeydown={(e) => {
            if ((e.key === "Enter" || e.key === " ") && e.target === e.currentTarget) {
              e.preventDefault();
              openConfirm(p);
            }
          }}
        >
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
              <Badge variant={conv}>{convictionLabel(conv)}</Badge>
              {#if stale}
                <Badge class="border-warning text-warning">STALE</Badge>
              {/if}
              {#if p.hint_kind === "default"}
                <Badge class="border-warning text-warning">DEFAULT HINT</Badge>
              {/if}
            </div>
            <div class="line2 mono">
              <span>QTY <b>{p.quantity}</b></span>
              <span>PRICE <b>{p.price != null ? fmtMoney(p.price) : "MKT"}</b></span>
              <span>TYPE <b>{p.order_type}</b></span>
              {#if stale && ageSeconds(p.timestamp) !== null}
                <span class="stale-time">{ageSeconds(p.timestamp)}s</span>
              {:else}
                <span>{timeStr(p.timestamp)}</span>
              {/if}
            </div>
          </div>
          <div class="row-actions">
            <Button
              variant="default"
              size="sm"
              class="min-w-16"
              disabled={busy || !canApprove}
              title={canApprove
                ? "Approve and place this proposal"
                : "OBSERVER never places orders — switch to PAPER or LIVE to approve"}
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
          {#if isLive}
            Approving places a <strong class="danger-text">REAL order</strong> on your brokerage
            account. Verify every field — it executes on confirmation.
          {:else}
            Approving routes this proposal to the {mode} engine. Nothing is placed automatically.
          {/if}
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
          <div class="sum-row"><span>MARGIN USED</span><b>{fmtMoney(risk.margin_used)}</b></div>
          <div class="sum-row"><span>MARGIN AVAIL</span><b>{risk.margin_available !== null ? fmtMoney(risk.margin_available) : "—"}</b></div>
          <div class="sum-row"><span>LOSS LIMIT</span><b class={risk.loss_limit_hit ? "down" : ""}>{fmtMoney(risk.loss_limit)}</b></div>
          <div class="sum-row"><span>ACTIVE POS</span><b>{risk.active_positions}/{risk.max_positions}</b></div>
        </div>
        {#if risk.loss_limit_hit}
          <p class="risk-alert">
            LOSS LIMIT HIT — daily P&L is below the configured loss limit. Proceed with caution.
          </p>
        {/if}
      {/if}

      <DialogFooter>
        <Button variant="ghost" onclick={() => (target = null)} disabled={busy}>Cancel</Button>
        <Button
          variant={isLive ? "danger" : "default"}
          onclick={confirmApprove}
          disabled={busy}
        >
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
  /* Mode chip — OBSERVER = faint, PAPER = info, LIVE = accent (pulsing dot). */
  .mode-chip {
    display: inline-flex;
    align-items: center;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    border: 1px solid var(--hairline-strong);
    border-radius: 4px;
    padding: 2px 6px;
  }
  .chip-observer {
    color: var(--faint);
    border-color: var(--hairline-strong);
  }
  .chip-paper {
    color: var(--info);
    border-color: var(--info);
  }
  .chip-live {
    color: var(--accent);
    border-color: var(--accent);
  }
  .chip-dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    margin-right: 4px;
    background: currentColor;
    animation: chip-pulse 1s ease-in-out infinite;
  }
  @keyframes chip-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.35;
    }
  }
  .observer-note {
    margin: 0;
    background: color-mix(in srgb, var(--info) 10%, var(--surface-card));
    border-bottom: 1px solid var(--hairline);
    color: var(--info);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.04em;
    padding: 6px 10px;
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
    /* Keyboard-first: Enter/Space on a focused row opens its confirm dialog. */
    border-radius: 4px;
  }
  .row:hover {
    background: var(--row-hover);
  }
  .row:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: -2px;
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
  .stale-time {
    color: var(--warning);
    font-weight: 600;
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
  .risk-alert {
    margin: 0;
    background: color-mix(in srgb, var(--danger) 10%, var(--surface-card));
    border: 1px solid var(--danger);
    border-radius: 4px;
    color: var(--danger);
    font-size: 11px;
    line-height: 1.5;
    padding: 8px 10px;
  }
  .danger-text {
    color: var(--danger);
    font-weight: 700;
  }
  .mono {
    font-family: "JetBrains Mono", "IBM Plex Mono", ui-monospace, monospace;
    font-variant-numeric: tabular-nums;
  }
  @media (prefers-reduced-motion: reduce) {
    .chip-dot {
      animation: none;
    }
  }
</style>
