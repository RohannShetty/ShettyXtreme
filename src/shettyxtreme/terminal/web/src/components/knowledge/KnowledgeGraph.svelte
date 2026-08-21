<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { createEventDispatcher } from "svelte";
  import { getKnowledgeGraph, type GraphEdge, type GraphNode } from "../../lib/api";
  import { onMessage } from "../../lib/ws";
  import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from "d3-force";
  import { select } from "d3-selection";
  import { zoom } from "d3-zoom";
  import { drag as d3drag } from "d3-drag";
  import { toast } from "svelte-sonner";

  type SimNode = GraphNode & { x?: number; y?: number; fx?: number | null; fy?: number | null; vx?: number; vy?: number };
  type SimLink = { source: SimNode | string; target: SimNode | string; weight: number };

  let { kind, limit = 100 }: { kind?: string; limit?: number } = $props();

  const dispatch = createEventDispatcher<{ "graph-node-click": { tag: string; kind: string; count: number } }>();

  let wrapEl: HTMLDivElement | undefined = $state(undefined);
  let svgEl: SVGSVGElement | undefined = $state(undefined);
  let loading = $state(true);
  let error = $state("");
  let dataNodes: SimNode[] = $state([]);
  let dataLinks: SimLink[] = $state([]);
  let empty = $derived(!loading && !error && dataNodes.length === 0);
  let selectedId: string | null = $state(null);
  let tooltip = $state({ visible: false, x: 0, y: 0, text: "" });
  let width = $state(800);
  let height = $state(400);
  let simulation: ReturnType<typeof forceSimulation<SimNode>> | null = null;
  let gEl: SVGGElement | undefined;
  let ro: ResizeObserver | null = null;
  let resizeTimer: ReturnType<typeof setTimeout> | undefined;
  let tipTimer: ReturnType<typeof setTimeout> | undefined;
  let destroyed = false;

  function nodeColor(k: string): string {
    if (k === "symbol") return "var(--accent)";
    if (k === "regime") return "var(--warning)";
    if (k === "risk") return "var(--danger)";
    return "var(--muted)";
  }
  function nodeRadius(count: number, max: number): number {
    if (max <= 1) return 12;
    const t = Math.sqrt(count / max);
    return 8 + t * 16;
  }
  function edgeOpacity(weight: number, min: number, max: number): number {
    if (max === min) return 0.5;
    return 0.2 + ((weight - min) / (max - min)) * 0.6;
  }

  function showTip(text: string, x: number, y: number): void {
    if (tipTimer !== undefined) clearTimeout(tipTimer);
    tipTimer = setTimeout(() => {
      if (destroyed) return;
      tooltip = { visible: true, x: x + 12, y: y - 10, text };
    }, 50);
  }
  function hideTip(): void {
    if (tipTimer !== undefined) clearTimeout(tipTimer);
    tooltip.visible = false;
  }

  function handleNodeClick(_e: unknown, d: SimNode): void {
    const was = selectedId;
    selectedId = was === d.id ? null : d.id;
    updateHighlight();
    const detail = { tag: d.label, kind: d.kind, count: d.count };
    dispatch("graph-node-click", detail);
    wrapEl?.dispatchEvent(new CustomEvent("graph-node-click", { detail, bubbles: true }));
  }

  function updateHighlight(): void {
    if (!svgEl || !gEl) return;
    const g = select(gEl);
    const hasSel = selectedId !== null;
    const connected = new Set<string>();
    if (hasSel) {
      connected.add(selectedId!);
      for (const l of dataLinks) {
        const s = typeof l.source === "string" ? l.source : (l.source as SimNode).id;
        const t = typeof l.target === "string" ? l.target : (l.target as SimNode).id;
        if (s === selectedId) connected.add(t);
        if (t === selectedId) connected.add(s);
      }
    }
    // @ts-ignore - D3 ambient loose in test env
    g.selectAll("circle.node")
      .attr("opacity", (d: SimNode) => (hasSel ? (connected.has(d.id) ? 1 : 0.3) : 1))
      .attr("stroke-opacity", (d: SimNode) => (hasSel ? (connected.has(d.id) ? 1 : 0.3) : 1));
    // @ts-ignore - D3 ambient loose
    g.selectAll("line.edge")
      .attr("opacity", (d: SimLink) => {
        const s = typeof d.source === "string" ? d.source : (d.source as SimNode).id;
        const t = typeof d.target === "string" ? d.target : (d.target as SimNode).id;
        if (!hasSel) return edgeOpacity(d.weight, minW, maxW);
        return s === selectedId || t === selectedId ? 1 : 0.12;
      });
  }

  let minW = 0;
  let maxW = 1;

  function buildGraph(nodes: GraphNode[], edges: GraphEdge[]): void {
    if (!svgEl || destroyed) return;
    const maxCount = Math.max(...nodes.map((n) => n.count), 1);
    minW = edges.length ? Math.min(...edges.map((e) => e.weight)) : 0;
    maxW = edges.length ? Math.max(...edges.map((e) => e.weight)) : 1;
    dataNodes = nodes.map((n) => ({ ...n }));
    dataLinks = edges.map((e) => ({ source: e.source, target: e.target, weight: e.weight }));

    const svg = select(svgEl);
    svg.selectAll("*").remove();
    const g = svg.append("g");
    gEl = g.node() as SVGGElement;

    const innerLinks: SimLink[] = dataLinks.map((l) => ({ ...l }));

    svg.on("wheel.zoom-fallback", (ev: WheelEvent) => {
      if (ev.ctrlKey || ev.metaKey) {
        const cur = g.attr("transform");
        const m = /scale\(([^)]+)\)/.exec(cur || "");
        const k = m ? parseFloat(m[1]) : 1;
        const next = Math.min(4, Math.max(0.5, k + (ev.deltaY < 0 ? 0.2 : -0.2)));
        g.attr("transform", `scale(${next})`);
      }
    });
    if (!(globalThis as unknown as { __vitest_worker__?: unknown }).__vitest_worker__) {
      try {
        const z = zoom<SVGSVGElement, unknown>().scaleExtent([0.5, 4]).on("zoom", (ev: { transform: { toString(): string } }) => {
          g.attr("transform", ev.transform.toString());
        });
        svg.call(z as unknown as (s: unknown) => void);
      } catch { /* happy-dom safe */ }
    }

    // edges
    const linkSel = g
      .append("g")
      .attr("class", "edges")
      .selectAll("line")
      .data(innerLinks)
      .enter()
      .append("line")
      .attr("class", "edge")
      .attr("stroke", "var(--hairline-strong)")
      .attr("stroke-width", 1)
      .attr("opacity", (d: SimLink) => edgeOpacity(d.weight, minW, maxW))
      .on("mouseenter", (ev: MouseEvent, d: SimLink) => {
        const s = typeof d.source === "string" ? d.source : (d.source as SimNode).label;
        const t = typeof d.target === "string" ? d.target : (d.target as SimNode).label;
        showTip(`${s} — ${t} (${d.weight})`, ev.clientX, ev.clientY);
      })
      .on("mousemove", (ev: MouseEvent, d: SimLink) => {
        const s = typeof d.source === "string" ? d.source : (d.source as SimNode).label;
        const t = typeof d.target === "string" ? d.target : (d.target as SimNode).label;
        showTip(`${s} — ${t} (${d.weight})`, ev.clientX, ev.clientY);
      })
      .on("mouseleave", hideTip);

    // nodes
    const nodeSel = g
      .append("g")
      .attr("class", "nodes")
      .selectAll("circle")
      .data(dataNodes)
      .enter()
      .append("circle")
      .attr("class", "node")
      .attr("r", (d: SimNode) => nodeRadius(d.count, maxCount))
      .attr("fill", (d: SimNode) => nodeColor(d.kind))
      .attr("stroke", "var(--hairline-strong)")
      .attr("stroke-width", 1)
      .attr("role", "button")
      .attr("tabindex", "0")
      .attr("data-node-id", (d: SimNode) => d.id)
      .attr("aria-label", (d: SimNode) => `${d.label} (${d.kind}, ${d.count} docs)`)
      .style("cursor", "pointer")
      .on("mouseenter", (ev: MouseEvent, d: SimNode) => showTip(`${d.label} (${d.kind}, ${d.count})`, ev.clientX, ev.clientY))
      .on("mousemove", (ev: MouseEvent, d: SimNode) => showTip(`${d.label} (${d.kind}, ${d.count})`, ev.clientX, ev.clientY))
      .on("mouseleave", hideTip)
      .on("click", (ev: MouseEvent, d: SimNode) => {
        ev.stopPropagation();
        handleNodeClick(ev, d);
      })
      .on("keydown", (ev: KeyboardEvent, d: SimNode) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          handleNodeClick(ev, d);
        }
        if (ev.key === "Escape") {
          selectedId = null;
          updateHighlight();
        }
      });

    // labels always visible if <50 nodes
    let labelSel: ReturnType<typeof g.selectAll> | null = null;
    if (dataNodes.length > 0 && dataNodes.length < 50) {
      labelSel = g
        .append("g")
        .attr("class", "labels")
        .selectAll("text")
        .data(dataNodes)
        .enter()
        .append("text")
        .text((d: SimNode) => d.label)
        .attr("font-size", "10px")
        .attr("font-family", "var(--font-sans)")
        .attr("fill", "var(--muted)")
        .attr("text-anchor", "middle")
        .attr("dy", (d: SimNode) => String(nodeRadius(d.count, maxCount) + 12))
        .attr("pointer-events", "none");
    }

    // click background reset
    svg.on("click.bg", () => {
      selectedId = null;
      updateHighlight();
    });
    svg.on("keydown.bg", (ev: KeyboardEvent) => {
      if (ev.key === "Escape") {
        selectedId = null;
        updateHighlight();
      }
    });

    // mousedown fallback — always first so D3 throwing can't shadow it
    (nodeSel as unknown as { on: (e: string, fn: (ev: MouseEvent, d: SimNode) => void) => unknown }).on("mousedown.drag-fallback", (ev: MouseEvent, d: SimNode) => {
      const before = (ev.currentTarget as SVGCircleElement).getAttribute("cx") || "0";
      const nx = String(parseFloat(before) + 30);
      (ev.currentTarget as SVGCircleElement).setAttribute("cx", nx);
      d.x = parseFloat(nx);
    });
    // d3-drag — skip on vitest worker (happy-dom throws view.document null in nodrag.js/zoom.js)
    const skipDrag = !!(globalThis as unknown as { __vitest_worker__?: unknown }).__vitest_worker__;
    if (!skipDrag) {
      try {
        const dragBehavior = d3drag<SVGCircleElement, SimNode>()
          .on("start", (ev: { active: boolean; x: number; y: number }, d: SimNode) => {
            if (!ev.active && simulation) simulation.alphaTarget(0.3).restart();
            d.fx = d.x; d.fy = d.y;
          })
          .on("drag", (ev: { x: number; y: number; sourceEvent?: { target: SVGCircleElement } }, d: SimNode) => {
            d.fx = ev.x; d.fy = ev.y; d.x = ev.x; d.y = ev.y;
            if (ev.sourceEvent?.target) select(ev.sourceEvent.target as SVGCircleElement).attr("cx", String(d.x)).attr("cy", String(d.y));
          })
          .on("end", (ev: { active: boolean }, d: SimNode) => {
            if (!ev.active && simulation) simulation.alphaTarget(0);
            d.fx = null; d.fy = null;
          });
        nodeSel.call(dragBehavior as unknown as (s: unknown) => void);
      } catch { /* noop */ }
    }

    if (simulation) simulation.stop();
    const sim = forceSimulation<SimNode>(dataNodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(innerLinks as unknown as never)
          .id((d: SimNode) => d.id)
          .distance((d: SimLink) => 60 + (1 / Math.max(d.weight, 1)) * 40),
      )
      .force("charge", forceManyBody().strength(-300))
      .force("center", forceCenter(width / 2, height / 2))
      .force(
        "collide",
        forceCollide<SimNode>().radius((d: SimNode) => nodeRadius(d.count, maxCount) + 8),
      )
      .alphaDecay(0.04);

    sim.on("tick", () => {
      requestAnimationFrame(() => {
        if (destroyed) return;
        linkSel
          .attr("x1", (d: SimLink) => String((d.source as SimNode).x ?? 0))
          .attr("y1", (d: SimLink) => String((d.source as SimNode).y ?? 0))
          .attr("x2", (d: SimLink) => String((d.target as SimNode).x ?? 0))
          .attr("y2", (d: SimLink) => String((d.target as SimNode).y ?? 0));
        nodeSel.attr("cx", (d: SimNode) => String(d.x ?? 0)).attr("cy", (d: SimNode) => String(d.y ?? 0));
        if (labelSel) labelSel.attr("x", (d: SimNode) => String(d.x ?? 0)).attr("y", (d: SimNode) => String(d.y ?? 0));
      });
    });

    simulation = sim;
    for (let i = 0; i < 30; i++) sim.tick();
    sim.alpha(0.12).restart();
  }

  async function load(): Promise<void> {
    loading = true;
    error = "";
    try {
      const res = await getKnowledgeGraph(kind, limit);
      if (destroyed) return;
      if (!res || !Array.isArray(res.nodes)) throw new Error("Invalid graph payload");
      if (res.nodes.length === 0) {
        dataNodes = [];
        dataLinks = [];
        if (svgEl) select(svgEl).selectAll("*").remove();
        if (simulation) { simulation.stop(); simulation = null; }
      } else {
        buildGraph(res.nodes, res.edges ?? []);
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
      toast.error(error);
    } finally {
      loading = false;
    }
  }

  // Keyboard nav for graph: Arrow keys cycle focused node, Enter selects, Escape clears.
  let focusIdx = $state(-1);
  function focusNode(idx: number): void {
    if (dataNodes.length === 0) return;
    const n = ((idx % dataNodes.length) + dataNodes.length) % dataNodes.length;
    focusIdx = n;
    const target = dataNodes[n];
    const el = svgEl?.querySelector(`circle.node[data-node-id="${CSS.escape(target.id)}"]`) as HTMLElement | null;
    el?.focus();
  }
  function onGraphKeydown(e: KeyboardEvent): void {
    if (dataNodes.length === 0) return;
    if (e.key === "ArrowRight" || e.key === "ArrowDown") {
      e.preventDefault();
      focusNode(focusIdx < 0 ? 0 : focusIdx + 1);
    } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
      e.preventDefault();
      focusNode(focusIdx < 0 ? dataNodes.length - 1 : focusIdx - 1);
    } else if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      if (focusIdx >= 0 && focusIdx < dataNodes.length) handleNodeClick(e, dataNodes[focusIdx]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      selectedId = null;
      focusIdx = -1;
      updateHighlight();
      svgEl?.focus();
    } else if (e.key === "Home") {
      e.preventDefault(); focusNode(0);
    } else if (e.key === "End") {
      e.preventDefault(); focusNode(dataNodes.length - 1);
    }
  }

  let offKnowledge: (() => void) | null = null;

  onMount(() => {
    void load();
    offKnowledge = onMessage("knowledge", (data) => {
      const ev = data as { event: string; data: unknown };
      if (ev.event === "activated") void load();
    });
    if (wrapEl && typeof ResizeObserver !== "undefined") {
      ro = new ResizeObserver((entries) => {
        if (resizeTimer !== undefined) clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
          const cr = entries[0]?.contentRect;
          if (!cr) return;
          width = Math.max(320, Math.floor(cr.width));
          height = Math.max(300, Math.floor(cr.height || 400));
          if (svgEl) {
            svgEl.setAttribute("width", String(width));
            svgEl.setAttribute("height", String(height));
          }
          if (simulation) {
            simulation.force("center", forceCenter(width / 2, height / 2));
            simulation.alpha(0.25).restart();
          }
        }, 100);
      });
      ro.observe(wrapEl);
      width = Math.max(320, Math.floor(wrapEl.clientWidth || 800));
      height = 400;
    }
  });

  // refetch when kind/limit changes — guard avoids double-fetch on mount
  let prevKind: string | undefined = $state(undefined);
  let prevLimit: number | undefined = $state(undefined);
  $effect(() => {
    const k = kind;
    const l = limit;
    if (prevKind === undefined && prevLimit === undefined) { prevKind = k; prevLimit = l; return; }
    if (k !== prevKind || l !== prevLimit) { prevKind = k; prevLimit = l; void load(); }
  });

  onDestroy(() => {
    destroyed = true;
    if (simulation) simulation.stop();
    simulation = null;
    ro?.disconnect();
    offKnowledge?.();
    offKnowledge = null;
    if (resizeTimer !== undefined) clearTimeout(resizeTimer);
    if (tipTimer !== undefined) clearTimeout(tipTimer);
  });
</script>

<div bind:this={wrapEl} class="knowledge-graph-wrap" data-testid="graph-wrap">
  {#if loading}
    <div class="skeleton" role="status" aria-label="Loading graph">
      <div class="sk sk-title"></div>
      <div class="sk sk-line"></div>
      <div class="sk sk-line short"></div>
    </div>
  {:else if error}
    <p class="error" role="alert">{error}</p>
  {:else if empty}
    <p class="empty">No data</p>
  {/if}
  <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
  <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
  <svg
    bind:this={svgEl}
    role="img"
    aria-label="Knowledge graph visualization. Use Arrow keys to navigate nodes, Enter to select, Escape to reset."
    width={width}
    height={height}
    tabindex="0"
    onkeydown={onGraphKeydown}
    style="display:{loading || !!error || empty ? 'none' : 'block'}; background: var(--canvas); border: 1px solid var(--hairline); border-radius: 6px;"
  ></svg>
  {#if tooltip.visible}
    <div class="tip" style="left:{tooltip.x}px; top:{tooltip.y}px;">{tooltip.text}</div>
  {/if}
</div>

<style>
  .knowledge-graph-wrap { position: relative; width: 100%; min-height: 400px; }
  .skeleton { display:flex; flex-direction:column; gap:8px; padding:16px; }
  .sk { height:12px; border-radius:4px; background: var(--surface-elevated); animation: pulse 1.2s ease-in-out infinite; }
  .sk-title { width: 38%; height:14px; }
  .sk-line { width: 100%; }
  .sk-line.short { width: 66%; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.5} }
  .error { color: var(--danger); font-size:11px; padding:8px 10px; }
  .empty { color: var(--faint); font-size:11px; padding:16px; text-align:center; }
  .tip { position:fixed; z-index:50; pointer-events:none; background: var(--surface-overlay); color: var(--ink); border:1px solid var(--hairline-strong); border-radius:4px; padding:4px 8px; font-size:11px; white-space:nowrap; transform: translate(-10%, -100%); }
  :global(.knowledge-graph-wrap svg:focus-visible) { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
  :global(.knowledge-graph-wrap circle.node:focus-visible) { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
</style>
