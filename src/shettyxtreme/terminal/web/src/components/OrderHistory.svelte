<script lang="ts">
  import { onMount } from "svelte";
  import { toast } from "svelte-sonner";
  import {
    getOrders,
    cancelOrder,
    exportOrders,
    type OrderRecord,
    type ExportFormat,
  } from "../lib/api";
  import { onMessage, isWsConnected } from "../lib/ws";
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import { RotateCw, Download, X } from "@lucide/svelte";
  import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
  } from "$lib/components/ui/dialog";
  import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
  } from "$lib/components/ui/select";

  let orders = $state<OrderRecord[]>([]);
  let error = $state("");
  let loading = $state(true);
  let filter = $state<string | null>(null);

  // Export state
  let exportFormat = $state<ExportFormat>("csv");
  let exportDays = $state<number>(30);
  let exporting = $state(false);

  // Cancel dialog state
  let cancelTarget = $state<OrderRecord | null>(null);
  let cancelBusy = $state(false);

  const FILTERS = [
    { id: null, label: "ALL" },
    { id: "FILLED", label: "FILLED" },
    { id: "REJECTED", label: "REJECTED" },
    { id: "CANCELLED", label: "CANCELLED" },
    { id: "OPEN", label: "OPEN" },
  ];

  const EXPORT_DAYS = [7, 30, 90];
  const POLL_MS = 10_000;

  onMount(() => {
    void load();
    const unsub = onMessage("order", handleOrderMessage);
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
      orders = await getOrders(filter ?? undefined);
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  function handleOrderMessage(data: unknown): void {
    const frame = data as { action?: string; order?: Partial<OrderRecord> & { order_id?: string } };
    const update = frame?.order ?? (data as Partial<OrderRecord> & { order_id?: string });
    const action = frame?.action || "updated";
    if (!update?.order_id) return;

    const statusFromAction =
      action === "placed" ? "OPEN" :
      action === "filled" ? "FILLED" :
      action === "rejected" ? "REJECTED" :
      action === "cancelled" ? "CANCELLED" :
      update.status || "OPEN";

    const idx = orders.findIndex((o) => o.order_id === update.order_id);
    if (idx >= 0) {
      orders[idx] = { ...orders[idx], ...update, status: update.status || statusFromAction };
    } else {
      // Newly placed order: synthesize a minimal record so it appears immediately.
      const placed: OrderRecord = {
        order_id: update.order_id,
        symbol: update.symbol || "",
        exchange: update.exchange || "",
        side: update.side || "",
        order_type: update.order_type || "",
        quantity: update.quantity ?? 0,
        price: update.price ?? 0,
        status: update.status || statusFromAction,
        filled_quantity: update.filled_quantity ?? 0,
        average_price: update.average_price ?? 0,
        tag: (update as { tag?: string | null }).tag ?? null,
        created_at: update.created_at || new Date().toISOString(),
        strike: update.strike ?? null,
        expiry: update.expiry ?? null,
        option_type: update.option_type ?? null,
        lot_size: update.lot_size ?? null,
        stop_loss: update.stop_loss ?? null,
        target: update.target ?? null,
        rationale: update.rationale ?? null,
        confidence: update.confidence ?? null,
      };
      orders = [placed, ...orders];
    }
    toast.info(`Order ${update.order_id} ${action}`);
  }

  function canCancel(status: string): boolean {
    const s = status.toUpperCase();
    return s === "OPEN" || s === "PARTIALLY_FILLED";
  }

  function confirmCancel(order: OrderRecord): void {
    cancelTarget = order;
  }

  async function doCancel(): Promise<void> {
    if (!cancelTarget) return;
    cancelBusy = true;
    try {
      const result = await cancelOrder(cancelTarget.order_id);
      if (result.cancelled) {
        const idx = orders.findIndex((o) => o.order_id === result.order_id);
        if (idx >= 0) {
          orders[idx] = { ...orders[idx], status: "CANCELLED" };
        }
        toast.success(`Order ${result.order_id} cancelled`);
      } else {
        toast.error(result.message || "Cancel failed");
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(msg);
    } finally {
      cancelBusy = false;
      cancelTarget = null;
    }
  }

  async function doExport(): Promise<void> {
    exporting = true;
    try {
      const file = await exportOrders(exportFormat, exportDays);
      const url = URL.createObjectURL(file);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.name;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success(`Downloaded ${file.name}`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      toast.error(`Export failed: ${msg}`);
    } finally {
      exporting = false;
    }
  }

  function setFilter(f: string | null): void {
    filter = f;
    void load();
  }

  function fmtMoney(v: number | null | undefined): string {
    if (v === null || v === undefined || !isFinite(v)) return "—";
    return v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

  function statusBadgeClass(status: string): string {
    switch (status) {
      case "FILLED": return "border-success text-success";
      case "REJECTED": return "border-danger text-danger";
      case "CANCELLED": return "border-warning text-warning";
      case "OPEN": return "border-info text-info";
      case "PARTIALLY_FILLED": return "border-info text-info";
      default: return "";
    }
  }
</script>

<section class="panel orders">
  <header class="panel-head">
    <div class="titles">
      <span class="eyebrow">EXECUTION</span>
      <h2>Order History</h2>
    </div>
    <div class="head-right">
      <div class="export-bar">
        <Select type="single" value={exportFormat} onValueChange={(v) => (exportFormat = v as ExportFormat)}>
          <SelectTrigger class="h-7 w-[70px] text-[11px]" aria-label="Export format">
            <span class="uppercase">{exportFormat}</span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="csv" label="CSV">CSV</SelectItem>
            <SelectItem value="json" label="JSON">JSON</SelectItem>
          </SelectContent>
        </Select>
        <Select type="single" value={String(exportDays)} onValueChange={(v) => (exportDays = Number(v))}>
          <SelectTrigger class="h-7 w-[90px] text-[11px]" aria-label="Export range">
            <span>Last {exportDays}d</span>
          </SelectTrigger>
          <SelectContent>
            {#each EXPORT_DAYS as d}
              <SelectItem value={String(d)} label="Last {d} days">Last {d} days</SelectItem>
            {/each}
          </SelectContent>
        </Select>
        <Button
          variant="secondary"
          size="sm"
          class="h-7 gap-1 text-[11px]"
          onclick={doExport}
          disabled={exporting || loading}
          aria-label="Export orders"
        >
          <Download class="size-3.5" />
          Export
        </Button>
      </div>
      <Button
        variant="ghost"
        size="icon"
        class="size-7 text-muted-foreground hover:text-ink"
        onclick={() => load()}
        aria-label="Refresh orders"
      >
        <RotateCw class="size-3.5" />
      </Button>
    </div>
  </header>

  <div class="filter-bar">
    {#each FILTERS as f}
      <button
        class="filter-btn"
        class:active={filter === f.id}
        onclick={() => setFilter(f.id)}
        type="button"
      >
        {f.label}
      </button>
    {/each}
  </div>

  {#if error}
    <p class="error">{error}</p>
  {:else if loading && orders.length === 0}
    <p class="empty">Loading…</p>
  {:else if orders.length === 0}
    <p class="empty">No orders{filter ? ` with status ${filter}` : ""}.</p>
  {:else}
    <ScrollArea class="min-h-0">
      <div class="rows">
        {#each orders as o (o.order_id)}
          <div class="order-row">
            <div class="order-main">
              <div class="order-line1">
                <span class="sym mono">{o.symbol}</span>
                {#if o.strike}
                  <span class="mono leg-strike">{o.strike}</span>
                {/if}
                {#if o.option_type}
                  <Badge class={o.option_type === "CE" ? "border-option-call text-option-call" : "border-option-put text-option-put"}>
                    {o.option_type}
                  </Badge>
                {/if}
                {#if o.expiry}
                  <span class="leg-expiry">{o.expiry}</span>
                {/if}
                <Badge
                  class={o.side === "BUY"
                    ? "border-side-buy text-side-buy"
                    : "border-side-sell text-side-sell"}
                >
                  {o.side}
                </Badge>
                <Badge class={statusBadgeClass(o.status)}>{o.status}</Badge>
              </div>
              <div class="order-line2 mono">
                <span>QTY <b>{o.quantity}</b></span>
                <span>FILLED <b>{o.filled_quantity}</b></span>
                <span>PRICE <b>{fmtMoney(o.average_price || o.price)}</b></span>
                <span>TYPE <b>{o.order_type}</b></span>
                {#if o.stop_loss || o.target}
                  <span class="leg-sltp">
                    SL <b class="sl-val">{o.stop_loss ? fmtMoney(o.stop_loss) : "—"}</b>
                    TGT <b class="tgt-val">{o.target ? fmtMoney(o.target) : "—"}</b>
                  </span>
                {/if}
                <span>{timeStr(o.created_at)}</span>
              </div>
              {#if o.rationale}
                <div class="order-line3" title={o.rationale}>{o.rationale}</div>
              {/if}
            </div>
            <div class="order-actions">
              {#if canCancel(o.status)}
                <Button
                  variant="danger"
                  size="sm"
                  class="h-6 gap-1 px-2 text-[11px]"
                  onclick={() => confirmCancel(o)}
                  aria-label={`Cancel order ${o.order_id}`}
                >
                  <X class="size-3" />
                  Cancel
                </Button>
              {:else}
                <Button
                  variant="secondary"
                  size="sm"
                  class="h-6 px-2 text-[11px]"
                  disabled
                >
                  {o.status}
                </Button>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    </ScrollArea>
  {/if}
</section>

<!-- Cancel confirmation dialog -->
<Dialog open={cancelTarget !== null} onOpenChange={(open) => { if (!open) cancelTarget = null; }}>
  <DialogContent class="sm:max-w-[420px]">
    <DialogHeader>
      <DialogTitle>Cancel order?</DialogTitle>
      <DialogDescription>
        {#if cancelTarget}
          This will cancel <span class="mono font-semibold">{cancelTarget.order_id}</span>
          for <span class="mono font-semibold">{cancelTarget.symbol}</span>
          ({cancelTarget.side} {cancelTarget.quantity} @ {fmtMoney(cancelTarget.price || cancelTarget.average_price)}).
        {/if}
      </DialogDescription>
    </DialogHeader>
    <DialogFooter>
      <Button
        variant="secondary"
        size="sm"
        onclick={() => (cancelTarget = null)}
        disabled={cancelBusy}
      >
        Keep order
      </Button>
      <Button
        variant="danger"
        size="sm"
        onclick={doCancel}
        disabled={cancelBusy}
      >
        {cancelBusy ? "Cancelling…" : "Cancel order"}
      </Button>
    </DialogFooter>
  </DialogContent>
</Dialog>

<style>
  .orders {
    display: flex;
    flex-direction: column;
    min-width: 0;
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
    gap: 8px;
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
    gap: 8px;
    flex-wrap: wrap;
    justify-content: flex-end;
  }
  .export-bar {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .filter-bar {
    display: flex;
    gap: 4px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--hairline);
  }
  .filter-btn {
    padding: 2px 8px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    cursor: pointer;
    transition: color 100ms, background 100ms;
  }
  .filter-btn:hover {
    color: var(--body);
    background: var(--row-hover);
  }
  .filter-btn.active {
    color: var(--ink);
    background: var(--surface-elevated);
    border-color: var(--hairline);
  }
  .rows {
    display: flex;
    flex-direction: column;
  }
  .order-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--hairline);
  }
  .order-main {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
    flex: 1;
  }
  .order-actions {
    flex-shrink: 0;
  }
  .order-line1 {
    display: flex;
    align-items: center;
    gap: 6px;
    flex-wrap: wrap;
  }
  .sym {
    color: var(--ink);
    font-size: 12px;
    font-weight: 500;
  }
  .order-line2 {
    display: flex;
    gap: 10px;
    font-size: 11px;
    color: var(--muted);
    white-space: nowrap;
    flex-wrap: wrap;
  }
  .order-line2 b {
    color: var(--ink);
    font-weight: 500;
    margin-left: 2px;
  }
  .order-line3 {
    font-size: 10px;
    color: var(--faint);
    line-height: 1.4;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
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
  .mono {
    font-family: "JetBrains Mono", "IBM Plex Mono", ui-monospace, monospace;
    font-variant-numeric: tabular-nums;
  }
  /* Semantic color tokens — follows price convention, independent of directional tokens. */
  :global(.text-price-up) { color: var(--price-up); }
  :global(.text-price-down) { color: var(--price-down); }
  .sl-val { color: var(--sl-level); }
  .tgt-val { color: var(--tgt-level); }
</style>
