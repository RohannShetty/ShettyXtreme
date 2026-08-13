<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { toast } from "svelte-sonner";
  import {
    approveProposal,
    executionMode,
    getProposals,
    rejectProposal,
    riskSummary,
    type Proposal,
    type RiskSummary,
  } from "../lib/api";
  import { onMessage } from "../lib/ws";
  import { Badge, type BadgeVariant } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
  } from "$lib/components/ui/dialog";
  import {
    Tabs,
    TabsContent,
    TabsList,
    TabsTrigger,
  } from "$lib/components/ui/tabs";
  import { RotateCw } from "@lucide/svelte";

  // Matches the backend staleness threshold (STALENESS_THRESHOLD_SEC = 30.0);
  // proposals older than this get a warning STALE chip (DESIGN §4).
  const STALE_MS = 30_000;

  type ProposalEvent = {
    action: "created" | "approved" | "rejected" | "expired";
    proposal: Proposal;
  };

  let proposals = $state<Proposal[]>([]);
  let history = $state<Proposal[]>([]);
  let historyLoading = $state(false);
  let historyError = $state("");
  let activeTab = $state<"active" | "history">("active");
  let historyStart = $state("");
  let historyEnd = $state("");
  let mode = $state("OBSERVER");
  let csrfToken = $state<string | null>(null);
  let risk: RiskSummary | null = $state(null);
  let error = $state("");
  let feedback = $state("");
  let target: Proposal | null = $state(null);
  let busy = $state(false);
  let now = $state(Date.now());
  let nowTimer: ReturnType<typeof setInterval> | undefined;
  let unsubscribeWs: (() => void) | undefined;

  let isLive = $derived(mode === "LIVE");
  // The backend refuses approvals in OBSERVER ("OBSERVER mode never places
  // orders"). Disable APPROVE there instead of surfacing a failed call.
  let canApprove = $derived(mode !== "OBSERVER");

  onMount(() => {
    void refresh();
    nowTimer = setInterval(() => (now = Date.now()), 1000);
    window.addEventListener("keydown", onWindowKey);
    unsubscribeWs = onMessage("proposal", handleProposalEvent);
  });

  onDestroy(() => {
    if (nowTimer) clearInterval(nowTimer);
    window.removeEventListener("keydown", onWindowKey);
    if (unsubscribeWs) unsubscribeWs();
  });

  function handleProposalEvent(data: unknown): void {
    const ev = data as ProposalEvent;
    if (!ev || typeof ev.action !== "string" || !ev.proposal) return;
    const p = ev.proposal;
    switch (ev.action) {
      case "created":
        if (!proposals.some((x) => x.id === p.id) && p.status === "PENDING") {
          proposals = [p, ...proposals];
          toast.info(`New proposal: ${p.side} ${p.symbol}`, {
            description: p.rationale ?? undefined,
          });
        }
        break;
      case "approved":
        proposals = proposals.filter((x) => x.id !== p.id);
        toast.success(`Proposal approved: ${p.side} ${p.symbol}`, {
          description: `${fmtLots(p)} → ${p.status}`,
        });
        break;
      case "rejected":
        proposals = proposals.filter((x) => x.id !== p.id);
        toast.error(`Proposal rejected: ${p.side} ${p.symbol}`, {
          description: p.reason || "Rejected by operator",
        });
        break;
      case "expired":
        proposals = proposals.filter((x) => x.id !== p.id);
        toast.warning(`Proposal expired: ${p.side} ${p.symbol}`, {
          description: p.reason || "Signal validity window closed",
        });
        break;
    }
    if (activeTab === "history") {
      void loadHistory();
    }
  }

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
        getProposals({ status: "PENDING" }),
        executionMode(),
        riskSummary().catch(() => null),
      ]);
      proposals = p;
      mode = m.mode;
      csrfToken = m.csrf_token;
      risk = r;
      error = "";
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function loadHistory(): Promise<void> {
    if (activeTab !== "history") return;
    historyLoading = true;
    historyError = "";
    try {
      history = await getProposals({
        status: ["APPROVED", "REJECTED", "EXPIRED"],
        start: historyStart || undefined,
        end: historyEnd || undefined,
      });
    } catch (err) {
      historyError = err instanceof Error ? err.message : String(err);
    } finally {
      historyLoading = false;
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

  function statusVariant(status: string): BadgeVariant {
    switch (status) {
      case "APPROVED":
        return "success";
      case "REJECTED":
        return "danger";
      case "EXPIRED":
        return "warning";
      default:
        return "info";
    }
  }

  function timeStr(ts: string | null): string {
    if (!ts) return "—";
    const d = new Date(ts);
    return isNaN(d.getTime()) ? "—" : d.toLocaleTimeString("en-IN", { hour12: false });
  }

  function dateStr(ts: string | null): string {
    if (!ts) return "—";
    const d = new Date(ts);
    return isNaN(d.getTime()) ? "—" : d.toLocaleDateString("en-IN");
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

  function fmtLots(p: Proposal): string {
    if (p.lot_size && p.lot_size > 0 && p.lots && p.lots > 0) {
      return `${p.lots} ${p.lots === 1 ? "lot" : "lots"} (${p.quantity} qty)`;
    }
    return `${p.quantity}`;
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

  <Tabs value={activeTab} onValueChange={(v) => { if (v === "active" || v === "history") { activeTab = v; if (v === "history") void loadHistory(); } }} class="flex flex-col min-h-0 flex-1">
    <TabsList class="mx-2 mt-2 w-auto justify-start">
      <TabsTrigger value="active">Active</TabsTrigger>
      <TabsTrigger value="history">History</TabsTrigger>
    </TabsList>

    <TabsContent value="active" class="flex flex-col min-h-0 flex-1 mt-0">
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
        <ScrollArea class="min-h-0 flex-1">
          <div class="rows">
            {#each proposals as p (p.id)}
              {@const stale = isStale(p.timestamp)}
              {@const conv = convictionVariant(p.conviction)}
              <div
                class="row"
                tabindex="0"
                role="button"
                aria-label={`${p.symbol} ${p.side} ${fmtLots(p)}${p.strike ? ` ${p.strike}${p.option_type || ""}` : ""} — press Enter to review and approve`}
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
                    {#if p.strike}
                      <span class="mono leg-strike">{p.strike}</span>
                    {/if}
                    {#if p.option_type}
                      <Badge class={p.option_type === "CE" ? "border-option-call text-option-call" : "border-option-put text-option-put"}>
                        {p.option_type}
                      </Badge>
                    {/if}
                    {#if p.expiry}
                      <span class="leg-expiry">{p.expiry}</span>
                    {/if}
                    <Badge
                      class={p.side === "BUY"
                        ? "border-side-buy text-side-buy"
                        : "border-side-sell text-side-sell"}
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
                    <span>QTY <b>{fmtLots(p)}</b></span>
                    {#if p.entry_premium}
                      <span>ENTRY <b>{fmtMoney(p.entry_premium)}</b></span>
                    {/if}
                    <span>PRICE <b>{p.price != null ? fmtMoney(p.price) : "MKT"}</b></span>
                    <span>TYPE <b>{p.order_type}</b></span>
                    {#if p.stop_loss || p.target}
                      <span class="leg-sltp">
                        SL <b class="sl-val">{p.stop_loss ? fmtMoney(p.stop_loss) : "—"}</b>
                        TGT <b class="tgt-val">{p.target ? fmtMoney(p.target) : "—"}</b>
                      </span>
                    {/if}
                    {#if p.confidence !== null && p.confidence !== undefined}
                      <span>CONF <b>{(p.confidence * 100).toFixed(0)}%</b></span>
                    {/if}
                    {#if p.ev_after_cost !== null && p.ev_after_cost !== undefined}
                      <span>EV <b class={p.ev_after_cost > 0 ? "price-up-val" : "price-down-val"}>{fmtMoney(p.ev_after_cost)}</b></span>
                    {/if}
                    {#if stale && ageSeconds(p.timestamp) !== null}
                      <span class="stale-time">{ageSeconds(p.timestamp)}s</span>
                    {:else}
                      <span>{timeStr(p.timestamp)}</span>
                    {/if}
                  </div>
                  {#if p.rationale}
                    <div class="line3" title={p.rationale}>{p.rationale}</div>
                  {/if}
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
        </ScrollArea>
      {/if}
    </TabsContent>

    <TabsContent value="history" class="flex flex-col min-h-0 flex-1 mt-0">
      <div class="history-controls">
        <Input
          type="date"
          bind:value={historyStart}
          aria-label="From date"
          class="w-36"
        />
        <span class="date-sep">to</span>
        <Input
          type="date"
          bind:value={historyEnd}
          aria-label="To date"
          class="w-36"
        />
        <Button
          variant="secondary"
          size="sm"
          onclick={() => loadHistory()}
          disabled={historyLoading}
        >
          {historyLoading ? "Loading…" : "Apply"}
        </Button>
      </div>

      {#if historyError}
        <p class="error">{historyError}</p>
      {:else if historyLoading && history.length === 0}
        <p class="empty">Loading history…</p>
      {:else if history.length === 0}
        <p class="empty">No closed proposals in this range.</p>
      {:else}
        <ScrollArea class="min-h-0 flex-1">
          <div class="rows">
            {#each history as h (h.id)}
              <div class="row history-row">
                <div class="row-main">
                  <div class="line1">
                    <span class="sym mono">{h.symbol}</span>
                    {#if h.strike}
                      <span class="mono leg-strike">{h.strike}</span>
                    {/if}
                    {#if h.option_type}
                      <Badge class={h.option_type === "CE" ? "border-option-call text-option-call" : "border-option-put text-option-put"}>
                        {h.option_type}
                      </Badge>
                    {/if}
                    <Badge
                      class={h.side === "BUY"
                        ? "border-side-buy text-side-buy"
                        : "border-side-sell text-side-sell"}
                    >
                      {h.side}
                    </Badge>
                    <Badge variant={statusVariant(h.status)}>{h.status}</Badge>
                  </div>
                  <div class="line2 mono">
                    <span>QTY <b>{fmtLots(h)}</b></span>
                    <span>PRICE <b>{h.price != null ? fmtMoney(h.price) : "MKT"}</b></span>
                    <span>TYPE <b>{h.order_type}</b></span>
                    <span>DATE <b>{dateStr(h.timestamp)}</b></span>
                    <span>TIME <b>{timeStr(h.timestamp)}</b></span>
                  </div>
                  {#if h.reason}
                    <div class="line3" title={h.reason}>{h.reason}</div>
                  {/if}
                </div>
              </div>
            {/each}
          </div>
        </ScrollArea>
      {/if}
    </TabsContent>
  </Tabs>

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
        {#if target.strike}
          <div class="sum-row"><span>STRIKE</span><b class="mono">{target.strike}</b></div>
        {/if}
        {#if target.option_type}
          <div class="sum-row"><span>TYPE</span><b class={target.option_type === "CE" ? "call-val" : "put-val"}>{target.option_type}</b></div>
        {/if}
        {#if target.expiry}
          <div class="sum-row"><span>EXPIRY</span><b>{target.expiry}</b></div>
        {/if}
        <div class="sum-row"><span>SIDE</span><b class={target.side === "BUY" ? "buy-val" : "sell-val"}>{target.side}</b></div>
        <div class="sum-row"><span>QUANTITY</span><b>{fmtLots(target)}</b></div>
        {#if target.entry_premium}
          <div class="sum-row"><span>ENTRY</span><b>{fmtMoney(target.entry_premium)}</b></div>
        {/if}
        <div class="sum-row"><span>PRICE</span><b>{target.price != null ? fmtMoney(target.price) : "MARKET"}</b></div>
        <div class="sum-row"><span>ORDER TYPE</span><b>{target.order_type}</b></div>
        <div class="sum-row"><span>PRODUCT</span><b>{target.product}</b></div>
        {#if target.stop_loss || target.target}
          <div class="sum-row"><span>SL / TGT</span><b><span class="sl-val">{target.stop_loss ? fmtMoney(target.stop_loss) : "—"}</span> / <span class="tgt-val">{target.target ? fmtMoney(target.target) : "—"}</span></b></div>
        {/if}
        {#if target.confidence !== null && target.confidence !== undefined}
          <div class="sum-row"><span>CONFIDENCE</span><b>{(target.confidence * 100).toFixed(0)}%</b></div>
        {/if}
        {#if target.ev_after_cost !== null && target.ev_after_cost !== undefined}
          <div class="sum-row"><span>EV AFTER COST</span><b class={target.ev_after_cost > 0 ? "price-up-val" : "price-down-val"}>{fmtMoney(target.ev_after_cost)}</b></div>
        {/if}
        {#if target.strategy}
          <div class="sum-row"><span>STRATEGY</span><b>{target.strategy}</b></div>
        {/if}
        {#if target.rationale}
          <div class="sum-row"><span>RATIONALE</span><b class="rationale-text">{target.rationale}</b></div>
        {/if}
      </div>

      {#if risk}
        <div class="summary mono risk">
          <div class="sum-row"><span>DAILY P&L</span><b class={risk.daily_pnl >= 0 ? "price-up-val" : "price-down-val"}>{fmtMoney(risk.daily_pnl)}</b></div>
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
          Confirm {target.side} {fmtLots(target)} {target.symbol}{target.strike ? ` ${target.strike}${target.option_type || ""}` : ""}
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
  .history-controls {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
  }
  .date-sep {
    font-size: 12px;
    color: var(--muted);
  }
  .rows {
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
  .history-row {
    cursor: default;
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
  .leg-strike {
    color: var(--ink);
    font-weight: 600;
    font-size: 11px;
  }
  .leg-expiry {
    color: var(--muted);
    font-size: 10px;
  }
  .leg-sltp {
    display: inline-flex;
    gap: 4px;
  }
  .leg-sltp b {
    font-weight: 600;
  }
  .line3 {
    font-size: 10px;
    color: var(--faint);
    line-height: 1.4;
    overflow: hidden;
    text-overflow: ellipsis;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  .rationale-text {
    font-weight: 400;
    font-size: 10px;
    line-height: 1.4;
    max-height: 2.8em;
    overflow: hidden;
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
  .price-up-val { color: var(--price-up); }
  .price-down-val { color: var(--price-down); }
  .call-val { color: var(--option-call); }
  .put-val { color: var(--option-put); }
  .buy-val { color: var(--side-buy); }
  .sell-val { color: var(--side-sell); }
  .sl-val { color: var(--sl-level); }
  .tgt-val { color: var(--tgt-level); }
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
