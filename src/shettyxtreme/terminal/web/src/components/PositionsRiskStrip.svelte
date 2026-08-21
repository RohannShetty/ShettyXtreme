<script lang="ts">
  import { onMount } from "svelte";
  import { toast } from "svelte-sonner";
  import { get, closePosition, getPositionHistory, type ClosedPositionRecord } from "../lib/api";
  import { onMessage, isWsConnected } from "../lib/ws";
  import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
  } from "$lib/components/ui/table";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import { Button } from "$lib/components/ui/button";
  import { Tabs, TabsContent, TabsList, TabsTrigger } from "$lib/components/ui/tabs";
  import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
  } from "$lib/components/ui/select";
  import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
  } from "$lib/components/ui/dialog";
  import { X } from "@lucide/svelte";
  import EmptyState from "./state/EmptyState.svelte";
  import LoadingState from "./state/LoadingState.svelte";
  import ErrorState from "./state/ErrorState.svelte";

  type Position = {
    symbol: string;
    exchange: string;
    quantity: number;
    net_quantity: number;
    buy_avg: number | null;
    m2m: number;
    pnl: number;
    product: string;
    strike?: number | null;
    option_type?: string | null;
    expiry?: string | null;
    instrument_type?: string | null;
    greeks?: {
      delta: number;
      gamma: number;
      theta: number;
      vega: number;
    } | null;
    stop_loss?: number | null;
    target?: number | null;
    rationale?: string | null;
    confidence?: number | null;
    signal_id?: string | null;
    lot_size?: number | null;
  };

  type Risk = {
    daily_pnl: number;
    margin_used: number;
    margin_available: number | null;
    loss_limit: number;
    loss_limit_hit: boolean;
    max_positions: number;
    active_positions: number;
  };

  let positions = $state<Position[]>([]);
  let risk = $state<Risk | null>(null);
  let error = $state("");
  let loading = $state(true);
  let activeTab = $state<"open" | "history">("open");

  // Close dialog state
  let closeTarget = $state<Position | null>(null);
  let closeBusy = $state(false);

  // History state
  let history = $state<ClosedPositionRecord[]>([]);
  let historyDays = $state<number>(30);
  let historyLoading = $state(false);
  let historyError = $state("");

  // Live-flash state: symbol -> 'up' | 'down' | ''
  let flashMap = $state<Record<string, "up" | "down" | "">>({});
  let lastM2m = $state<Record<string, number>>({});
  let lastPnl = $state<Record<string, number>>({});

  const HISTORY_DAY_OPTIONS = [7, 30, 90];
  const POLL_MS = 30_000;
  const FLASH_MS = 150;

  onMount(() => {
    void load();
    const unsub = onMessage("position", handlePositionMessage);
    const poll = window.setInterval(() => {
      if (!isWsConnected()) void load();
    }, POLL_MS);
    return () => {
      unsub();
      window.clearInterval(poll);
    };
  });

  async function load(): Promise<void> {
    error = "";
    loading = true;
    try {
      [positions, risk] = await Promise.all([
        get<Position[]>("/api/execution/positions"),
        get<Risk>("/api/execution/risk"),
      ]);
      // Seed flash baseline so the initial load does not flash.
      for (const p of positions) {
        lastM2m[p.symbol] = p.m2m;
        lastPnl[p.symbol] = p.pnl;
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  function handlePositionMessage(data: unknown): void {
    const update = data as Partial<Position> & { symbol?: string };
    const symbol = update?.symbol;
    if (!symbol) return;

    const idx = positions.findIndex((p) => p.symbol === symbol);
    if (idx < 0) {
      // New position: refresh from the server to get full greeks/context.
      void load();
      return;
    }

    const current = positions[idx];
    const next: Position = { ...current };
    if (update.net_quantity !== undefined) next.net_quantity = update.net_quantity;
    if (update.m2m !== undefined) next.m2m = update.m2m;
    if (update.pnl !== undefined) next.pnl = update.pnl;

    // Tick-flash when a value moves.
    const prevM2m = lastM2m[symbol] ?? current.m2m;
    const prevPnl = lastPnl[symbol] ?? current.pnl;
    if (next.m2m !== prevM2m || next.pnl !== prevPnl) {
      flashMap[symbol] = (next.pnl > prevPnl || next.m2m > prevM2m) ? "up" : "down";
      window.setTimeout(() => {
        flashMap[symbol] = "";
      }, FLASH_MS);
    }
    lastM2m[symbol] = next.m2m;
    lastPnl[symbol] = next.pnl;

    positions[idx] = next;
  }

  async function loadHistory(): Promise<void> {
    historyError = "";
    historyLoading = true;
    try {
      history = await getPositionHistory(historyDays);
    } catch (err) {
      historyError = err instanceof Error ? err.message : String(err);
    } finally {
      historyLoading = false;
    }
  }

  function onTabChange(tab: string): void {
    if (tab === "open" || tab === "history") {
      activeTab = tab;
      if (tab === "history" && history.length === 0) {
        void loadHistory();
      }
    }
  }

  function confirmClose(pos: Position): void {
    closeTarget = pos;
  }

  async function doClose(): Promise<void> {
    if (!closeTarget) return;
    closeBusy = true;
    try {
      await closePosition(closeTarget.symbol);
      toast.success(`Position ${closeTarget.symbol} closed`);
      await load();
      if (activeTab === "history") void loadHistory();
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`Close failed: ${msg}`);
    } finally {
      closeBusy = false;
      closeTarget = null;
    }
  }

  function pnlClass(value: number): string {
    return value > 0 ? "price-up" : value < 0 ? "price-down" : "";
  }

  function flashClass(symbol: string): string {
    const f = flashMap[symbol];
    return f === "up" ? "flash-up" : f === "down" ? "flash-down" : "";
  }

  function fmtMoney(value: number): string {
    const sign = value > 0 ? "+" : "";
    return `${sign}${value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  function fmtAvg(value: number): string {
    return value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function fmtGreek(value: number | undefined): string {
    if (value === undefined || !isFinite(value) || value === 0) return "—";
    return value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function fmtDate(ts: string | null): string {
    if (!ts) return "—";
    const d = new Date(ts);
    return isNaN(d.getTime()) ? "—" : d.toLocaleString("en-IN", { hour12: false });
  }

  let marginUnknown = $derived(risk !== null && risk.margin_available === null);
  let marginRatio = $derived(
    risk && risk.margin_available !== null && risk.margin_used + risk.margin_available > 0
      ? risk.margin_used / (risk.margin_used + risk.margin_available)
      : 0,
  );
  let marginBreach = $derived(
    risk !== null &&
      risk.margin_available !== null &&
      risk.margin_used > risk.margin_available,
  );
  let marginClass = $derived(marginBreach ? "ratio-breach" : marginRatio > 0.8 ? "ratio-warn" : "");
</script>

<section class="strip">
  <Tabs value={activeTab} onValueChange={onTabChange} class="pos-table">
    <TabsList class="mx-0 mt-0 mb-1 w-auto justify-start bg-transparent p-0 gap-1">
      <TabsTrigger value="open" class="tab-trigger">Open</TabsTrigger>
      <TabsTrigger value="history" class="tab-trigger">History</TabsTrigger>
    </TabsList>

    <TabsContent value="open" class="flex flex-col min-h-0 flex-1 mt-0">
      <ScrollArea class="flex-1 min-h-0">
        {#if loading && positions.length === 0}
          <LoadingState label="Loading positions…" rows={3} />
        {:else if positions.length === 0}
          <EmptyState message="No open positions." />
        {:else}
          <Table>
            <TableHeader>
              <TableRow class="hover:bg-transparent">
                <TableHead>Symbol</TableHead>
                <TableHead class="text-right" title="Strike price">Strike</TableHead>
                <TableHead class="text-right" title="Option type">Type</TableHead>
                <TableHead class="text-right" title="Expiry date">Expiry</TableHead>
                <TableHead class="text-right">Qty</TableHead>
                <TableHead class="text-right">Avg</TableHead>
                <TableHead class="text-right">M2M</TableHead>
                <TableHead class="text-right">P&L</TableHead>
                <TableHead class="text-right greek-col-head" title="Position Delta">Δ</TableHead>
                <TableHead class="text-right greek-col-head" title="Position Gamma">Γ</TableHead>
                <TableHead class="text-right greek-col-head" title="Position Theta (daily)">Θ</TableHead>
                <TableHead class="text-right greek-col-head" title="Position Vega">V</TableHead>
                <TableHead class="text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {#each positions as p (p.symbol)}
                {@const flash = flashClass(p.symbol)}
                <TableRow class={flash}>
                  <TableCell class="font-mono font-semibold text-ink">{p.symbol}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums">{p.strike ?? "—"}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums {p.option_type === 'CE' ? 'text-option-call' : p.option_type === 'PE' ? 'text-option-put' : ''}">{p.option_type ?? "—"}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums text-xs">{p.expiry ?? "—"}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums">{p.net_quantity}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums">{p.buy_avg ? fmtAvg(p.buy_avg) : "—"}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums {pnlClass(p.m2m)}">{fmtMoney(p.m2m)}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums {pnlClass(p.pnl)}">{fmtMoney(p.pnl)}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums greek-val">{fmtGreek(p.greeks?.delta)}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums greek-val">{fmtGreek(p.greeks?.gamma)}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums greek-val">{fmtGreek(p.greeks?.theta)}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums greek-val">{fmtGreek(p.greeks?.vega)}</TableCell>
                  <TableCell class="text-right">
                    <Button
                      variant="danger"
                      size="sm"
                      class="h-6 gap-1 px-2 text-[11px]"
                      onclick={() => confirmClose(p)}
                      aria-label={`Close position ${p.symbol}`}
                    >
                      <X class="size-3" />
                      Close
                    </Button>
                  </TableCell>
                </TableRow>
              {/each}
            </TableBody>
          </Table>
        {/if}
      </ScrollArea>
    </TabsContent>

    <TabsContent value="history" class="flex flex-col min-h-0 flex-1 mt-0">
      <div class="history-head">
        <Select type="single" value={String(historyDays)} onValueChange={(v) => { historyDays = Number(v); void loadHistory(); }}>
          <SelectTrigger class="h-7 w-[110px] text-[11px]" aria-label="History range">
            <span>Last {historyDays} days</span>
          </SelectTrigger>
          <SelectContent>
            {#each HISTORY_DAY_OPTIONS as d}
              <SelectItem value={String(d)} label="Last {d} days">Last {d} days</SelectItem>
            {/each}
          </SelectContent>
        </Select>
      </div>
      <ScrollArea class="flex-1 min-h-0">
        {#if historyLoading && history.length === 0}
          <LoadingState label="Loading history…" rows={3} />
        {:else if historyError && history.length === 0}
          <ErrorState message={historyError} onRetry={loadHistory} />
        {:else if history.length === 0}
          <EmptyState message="No closed positions for the selected range." />
        {:else}
          <Table>
            <TableHeader>
              <TableRow class="hover:bg-transparent">
                <TableHead>Symbol</TableHead>
                <TableHead class="text-right">Qty</TableHead>
                <TableHead class="text-right">Entry</TableHead>
                <TableHead class="text-right">Exit</TableHead>
                <TableHead class="text-right">Realized P&L</TableHead>
                <TableHead class="text-right">Opened</TableHead>
                <TableHead class="text-right">Closed</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {#each history as h (h.symbol + h.closed_at)}
                <TableRow>
                  <TableCell class="font-mono font-semibold text-ink">{h.symbol}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums">{h.quantity}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums">{fmtAvg(h.entry_price)}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums">{fmtAvg(h.exit_price)}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums {pnlClass(h.realized_pnl)}">{fmtMoney(h.realized_pnl)}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums text-xs">{fmtDate(h.opened_at)}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums text-xs">{fmtDate(h.closed_at)}</TableCell>
                </TableRow>
              {/each}
            </TableBody>
          </Table>
        {/if}
      </ScrollArea>
    </TabsContent>
  </Tabs>

  <div class="risk-block">
    <h2>Risk</h2>
    {#if error}
      <ErrorState message={error} onRetry={load} />
    {:else if loading && risk === null}
      <LoadingState label="Loading risk…" rows={2} />
    {:else if risk}
      <div class="row">
        <span class="label">DAILY P&L</span>
        <span class="num value {pnlClass(risk.daily_pnl)}">{fmtMoney(risk.daily_pnl)}</span>
      </div>
      <div class="row">
        <span class="label">MARGIN</span>
        <div class="margin">
          <div class="bar">
            <div
              class="fill {marginClass}"
              style="width: {marginUnknown ? 0 : Math.min(marginRatio * 100, 100)}%"
            ></div>
          </div>
          <span class="num">
            {fmtMoney(risk.margin_used)} / {marginUnknown ? "—" : fmtMoney(risk.margin_available ?? 0)}
          </span>
        </div>
      </div>
      <div class="row chips">
        {#if risk.loss_limit_hit}
          <span class="chip chip-danger">LOSS LIMIT HIT</span>
        {/if}
        {#if marginUnknown}
          <span class="chip chip-mute">MARGIN UNKNOWN</span>
        {:else if marginBreach}
          <span class="chip chip-danger">MARGIN BREACH</span>
        {:else if marginRatio > 0.8}
          <span class="chip chip-warn">MARGIN > 80%</span>
        {/if}
        <span class="chip chip-info">{risk.active_positions}/{risk.max_positions} POSITIONS</span>
      </div>
    {:else}
      <EmptyState message="No risk data." />
    {/if}
  </div>
</section>

<!-- Close confirmation dialog -->
<Dialog open={closeTarget !== null} onOpenChange={(open) => { if (!open) closeTarget = null; }}>
  <DialogContent class="sm:max-w-[420px]">
    <DialogHeader>
      <DialogTitle>Close position?</DialogTitle>
      <DialogDescription>
        {#if closeTarget}
          This will place an opposite-side market order to close
          <span class="mono font-semibold">{closeTarget.symbol}</span>
          ({closeTarget.net_quantity > 0 ? "LONG" : "SHORT"} {Math.abs(closeTarget.net_quantity)} qty).
        {/if}
      </DialogDescription>
    </DialogHeader>
    <DialogFooter>
      <Button
        variant="secondary"
        size="sm"
        onclick={() => (closeTarget = null)}
        disabled={closeBusy}
      >
        Keep position
      </Button>
      <Button
        variant="danger"
        size="sm"
        onclick={doClose}
        disabled={closeBusy}
      >
        {closeBusy ? "Closing…" : "Close position"}
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>

<style>
  .strip {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(300px, 360px);
    gap: 12px;
    min-height: 240px;
    padding: 10px;
    height: 100%;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-radius: 6px;
  }
  .pos-table,
  .risk-block {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  h2 {
    margin: 0 0 6px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .history-head {
    display: flex;
    justify-content: flex-end;
    padding: 0 0 6px;
  }
  .risk-block {
    gap: 8px;
    border-left: 1px solid var(--hairline);
    padding-left: 12px;
  }
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .label {
    color: var(--muted);
    font-size: 10px;
    letter-spacing: 0.06em;
    white-space: nowrap;
  }
  .value {
    font-size: 13px;
    font-weight: 600;
  }
  .margin {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex: 1;
    align-items: flex-end;
  }
  .bar {
    width: 100%;
    height: 5px;
    background: var(--canvas-raised);
    border-radius: 3px;
    overflow: hidden;
  }
  .fill {
    height: 100%;
    background: var(--accent);
    transition: width 120ms ease-out;
  }
  .fill.ratio-warn {
    background: var(--warning);
  }
  .fill.ratio-breach {
    background: var(--danger);
  }
  .chips {
    flex-wrap: wrap;
  }
  .chip {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.05em;
    border-radius: 4px;
    padding: 2px 6px;
    white-space: nowrap;
  }
  .chip-danger {
    color: var(--danger);
    border: 1px solid var(--danger);
  }
  .chip-warn {
    color: var(--warning);
    border: 1px solid var(--warning);
  }
  .chip-info {
    color: var(--info);
    border: 1px solid var(--info);
  }
  .chip-mute {
    color: var(--faint);
    border: 1px solid var(--hairline-strong);
  }
  /* Tick flash: transient background tint fades to row bg over 150ms. */
  :global(.flash-up) {
    animation: flashUp 150ms ease-out forwards;
  }
  :global(.flash-down) {
    animation: flashDown 150ms ease-out forwards;
  }
  @keyframes flashUp {
    from { background-color: var(--flash-up); }
    to { background-color: transparent; }
  }
  @keyframes flashDown {
    from { background-color: var(--flash-down); }
    to { background-color: transparent; }
  }
  /* Greek column headers — Δ/Γ/Θ/V in the positions strip. */
  :global(.greek-col-head) {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    letter-spacing: 0.04em;
  }
  /* Greek value cells — secondary data, slightly muted. */
  .greek-val {
    color: var(--faint);
    font-size: 11px;
  }
  /* Compact tab triggers for the positions strip. */
  :global(.tab-trigger) {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 4px 10px;
    color: var(--muted);
    border-bottom: 2px solid transparent;
    border-radius: 0;
    background: transparent;
  }
  :global(.tab-trigger[data-state="active"]) {
    color: var(--ink);
    border-bottom-color: var(--accent);
  }
</style>
