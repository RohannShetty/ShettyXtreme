<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "../lib/api";

  type Gap = { symbol: string; gap_type: string; gap_percent: number; direction: string };
  type Cluster = { symbol: string; cluster_type: string; strength: number; source_count: number };
  type Alert = { alert_type: string; severity: string; message: string; timestamp: string };

  let gaps: Gap[] = [];
  let clusters: Cluster[] = [];
  let alerts: Alert[] = [];
  let error = "";

  onMount(() => {
    load();
  });

  async function load(): Promise<void> {
    error = "";
    try {
      const [g, c, a] = await Promise.all([
        get<Gap[]>("/api/scanner/gaps"),
        get<Cluster[]>("/api/scanner/clusters"),
        get<Alert[]>("/api/scanner/alerts"),
      ]);
      gaps = g;
      clusters = c;
      alerts = a;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  function severityClass(severity: string): string {
    const s = String(severity).toUpperCase();
    return s === "HIGH" ? "sev-high" : s === "MEDIUM" ? "sev-med" : "sev-low";
  }

  function dirClass(direction: string): string {
    return String(direction).toLowerCase().includes("down") ? "price-down" : "price-up";
  }
</script>

<section class="panel scanner">
  <header class="panel-head">
    <h2>Scanner</h2>
    <button class="refresh" on:click={load} title="Refresh">↻</button>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <div class="cols">
    <div class="col">
      <h3>Gaps <span class="count mono">{gaps.length}</span></h3>
      <ul>
        {#each gaps as g (g.symbol + g.gap_type + g.gap_percent)}
          <li>
            <span class="ticker">{g.symbol}</span>
            <span class="tag">{g.gap_type}</span>
            <span class="num {dirClass(g.direction)}">{g.gap_percent > 0 ? "+" : ""}{g.gap_percent.toFixed(2)}%</span>
          </li>
        {/each}
        {#if gaps.length === 0}
          <li class="empty">No gaps detected.</li>
        {/if}
      </ul>
    </div>

    <div class="col">
      <h3>Clusters <span class="count mono">{clusters.length}</span></h3>
      <ul>
        {#each clusters as c (c.symbol + c.cluster_type)}
          <li>
            <span class="ticker">{c.symbol}</span>
            <span class="tag">{c.cluster_type}</span>
            <span class="num">{c.strength.toFixed(1)} / 10</span>
          </li>
        {/each}
        {#if clusters.length === 0}
          <li class="empty">No clusters found.</li>
        {/if}
      </ul>
    </div>

    <div class="col">
      <h3>Alerts <span class="count mono">{alerts.length}</span></h3>
      <ul>
        {#each alerts as a (a.message + a.timestamp)}
          <li>
            <span class="tag {severityClass(a.severity)}">{a.severity}</span>
            <span class="msg">{a.message}</span>
          </li>
        {/each}
        {#if alerts.length === 0}
          <li class="empty">No alerts.</li>
        {/if}
      </ul>
    </div>
  </div>
</section>

<style>
  .scanner {
    display: flex;
    flex-direction: column;
    min-width: 320px;
    min-height: 0;
    flex: 1 1 0;
    border-radius: 6px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
  }
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
  }
  .panel-head h2 {
    margin: 0;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .refresh {
    background: none;
    border: 1px solid var(--hairline);
    border-radius: 4px;
    color: var(--muted);
    cursor: pointer;
    padding: 2px 8px;
    font-size: 13px;
  }
  .refresh:hover {
    color: var(--ink);
    border-color: var(--hairline-strong);
  }
  .cols {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 10px;
  }
  .col h3 {
    margin: 0 0 6px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.07em;
    color: var(--faint);
    text-transform: uppercase;
  }
  .count {
    color: var(--faint);
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 0;
    font-size: 11px;
    border-bottom: 1px solid var(--hairline);
    min-height: 26px;
  }
  .ticker {
    color: var(--ink);
    font-weight: 600;
    min-width: 70px;
  }
  .tag {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    border: 1px solid var(--hairline-strong);
    border-radius: 4px;
    padding: 1px 5px;
  }
  .sev-high {
    color: var(--danger);
    border-color: var(--danger);
  }
  .sev-med {
    color: var(--warning);
    border-color: var(--warning);
  }
  .sev-low {
    color: var(--muted);
  }
  .msg {
    color: var(--body);
    flex: 1;
  }
  .empty {
    color: var(--faint);
    border-bottom: none;
  }
  .error {
    color: var(--danger);
    font-size: 11px;
    padding: 8px 10px;
    margin: 0;
  }
</style>
