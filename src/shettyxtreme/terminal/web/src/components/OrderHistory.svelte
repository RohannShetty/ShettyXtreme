<script lang="ts">
  import { onMount } from "svelte";
  import { getOrders, type OrderRecord } from "../lib/api";
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import { RotateCw } from "@lucide/svelte";

  let orders = $state<OrderRecord[]>([]);
  let error = $state("");
  let loading = $state(true);
  let filter = $state<string | null>(null);

  const FILTERS = [
    { id: null, label: "ALL" },
    { id: "FILLED", label: "FILLED" },
    { id: "REJECTED", label: "REJECTED" },
    { id: "CANCELLED", label: "CANCELLED" },
    { id: "OPEN", label: "OPEN" },
  ];

  onMount(() => {
    void load();
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

  function fmtMoney(v: number | null | undefined): string {
    if (v === null || v === undefined || !isFinite(v)) return "—";
    return v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function timeStr(ts: string | null): string {
    if (!ts) return "—";
    const d = new Date(ts);
    return isNaN(d.getTime()) ? "—" : d.toLocaleTimeString("en-IN", { hour12: false });
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

  function setFilter(f: string | null): void {
    filter = f;
    void load();
  }
</script>

<section class="panel orders">
  <header class="panel-head">
    <div class="titles">
      <span class="eyebrow">EXECUTION</span>
      <h2>Order History</h2>
    </div>
    <div class="head-right">
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
          </div>
        {/each}
      </div>
    </ScrollArea>
  {/if}
</section>

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
  }
  .order-line1 {
    display: flex;
    align-items: center;
    gap: 6px;
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
