/**
 * Lightweight SVG chart utilities for the analytics panel.
 *
 * No external charting dependency — everything is plain SVG driven by CSS
 * design tokens (var(--accent), var(--success), etc.) so the charts honor
 * dark/light theme and the Indian price convention automatically.
 *
 * All functions return an SVG string intended for {@html ...} rendering.
 */

export type TimePoint = { x: Date | number; y: number };

export type LineBand = {
  min: number;
  max: number;
  color: string;
  label?: string;
};

export type LineSeries = {
  key: string;
  points: TimePoint[];
  color: string;
  dashed?: boolean;
};

export type LineChartOptions = {
  width?: number;
  height?: number;
  /** @deprecated alias for margin — kept for backward compatibility with GreeksPanel. */
  padding?: { top: number; right: number; bottom: number; left: number };
  margin?: { top: number; right: number; bottom: number; left: number };
  yMin?: number;
  yMax?: number;
  yTickCount?: number;
  /** Backward-compatible alias for yTickCount. */
  gridLines?: number;
  xTickCount?: number;
  yFormatter?: (n: number) => string;
  /** Backward-compatible alias for yFormatter. */
  formatY?: (n: number) => string;
  xFormatter?: (v: Date | number) => string;
  /** Backward-compatible alias for xFormatter. */
  formatX?: (v: number) => string;
  lineColor?: string;
  /** Backward-compatible alias for lineColor. */
  stroke?: string;
  markerColor?: string;
  bands?: LineBand[];
  /** Optional area fill under the line. */
  fill?: string;
  strokeWidth?: number;
  ariaLabel?: string;
  title?: string;
};

export type MultiLineChartOptions = Omit<
  LineChartOptions,
  "lineColor" | "markerColor" | "stroke" | "fill"
> & {
  series: LineSeries[];
};

export type RegimeEntry = {
  timestamp: string;
  regime: string;
  confidence?: number | null;
};

export type RegimeColorMap = Record<string, string>;

export type RegimeTimelineOptions = {
  width?: number;
  height?: number;
  colors?: RegimeColorMap;
  ariaLabel?: string;
  title?: string;
  now?: Date;
};

const DEFAULT_W = 640;
const DEFAULT_H = 220;
const DEFAULT_MARGIN = { top: 24, right: 16, bottom: 36, left: 44 };

const DEFAULT_REGIME_COLORS: RegimeColorMap = {
  trending_up: "var(--success)",
  trending_down: "var(--danger)",
  range_bound: "var(--warning)",
  volatile: "var(--accent)",
};

/** Color-blind-safe dash patterns for multi-series lines. */
const LINE_DASH_PATTERNS = ["", "4 3", "2 2", "6 2 2 2", "3 3"];

/** Color-blind-safe marker shapes for multi-series lines. */
const MARKER_SHAPES = ["circle", "square", "diamond", "triangle"];

/** Pattern fills for regime timeline segments (color-blind aid). */
const REGIME_PATTERNS: Record<string, string> = {
  trending_up: "url(#pattern-up)",
  trending_down: "url(#pattern-down)",
  range_bound: "url(#pattern-range)",
  volatile: "url(#pattern-volatile)",
};

function clamp(n: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, n));
}

function toTime(p: TimePoint): number {
  return typeof p.x === "number" ? p.x : p.x.getTime();
}

function createScale(domain: [number, number], range: [number, number]) {
  const d0 = domain[0];
  const d1 = domain[1] === d0 ? d0 + 1 : domain[1];
  const r0 = range[0];
  const r1 = range[1];
  return (v: number) => r0 + ((v - d0) * (r1 - r0)) / (d1 - d0);
}

function linearTicks(min: number, max: number, count: number): number[] {
  const step = (max - min) / count;
  return Array.from({ length: count + 1 }, (_, i) => min + step * i);
}

function defaultYFormatter(n: number): string {
  return n.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function defaultXLabel(d: Date | number, spanMs: number): string {
  const date = typeof d === "number" ? new Date(d) : d;
  if (spanMs < 24 * 60 * 60 * 1000) {
    return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function escapeXml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

const TEXT_STYLE = `font-family="var(--font-mono)" font-variant-numeric="tabular-nums" font-size="10" fill="var(--muted)"`;

function linePath(points: TimePoint[], sx: (t: number) => number, sy: (v: number) => number): string {
  if (points.length === 0) return "";
  const first = points[0];
  let d = `M ${sx(toTime(first))} ${sy(first.y)}`;
  for (let i = 1; i < points.length; i++) {
    const p = points[i];
    d += ` L ${sx(toTime(p))} ${sy(p.y)}`;
  }
  return d;
}

function areaPath(
  points: TimePoint[],
  sx: (t: number) => number,
  sy: (v: number) => number,
  bottom: number,
): string {
  if (points.length === 0) return "";
  const first = points[0];
  const last = points[points.length - 1];
  let d = `M ${sx(toTime(first))} ${bottom} L ${sx(toTime(first))} ${sy(first.y)}`;
  for (let i = 1; i < points.length; i++) {
    const p = points[i];
    d += ` L ${sx(toTime(p))} ${sy(p.y)}`;
  }
  d += ` L ${sx(toTime(last))} ${bottom} Z`;
  return d;
}

function resolveMargin(options: LineChartOptions) {
  return options.margin ?? options.padding ?? DEFAULT_MARGIN;
}

/**
 * Single-series line chart with optional horizontal bands and a current-value
 * marker at the last data point.
 */
export function lineChart(points: TimePoint[], options: LineChartOptions = {}): string {
  const W = options.width ?? DEFAULT_W;
  const H = options.height ?? DEFAULT_H;
  const M = resolveMargin(options);
  const plotLeft = M.left;
  const plotRight = W - M.right;
  const plotTop = M.top;
  const plotBottom = H - M.bottom;
  const plotW = plotRight - plotLeft;
  const plotH = plotBottom - plotTop;

  if (points.length === 0) {
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${escapeXml(options.ariaLabel ?? "Empty chart")}"><title>${escapeXml(options.title ?? "Chart")}</title><text x="${W / 2}" y="${H / 2}" text-anchor="middle" ${TEXT_STYLE}>No data</text></svg>`;
  }

  const xs = points.map((p) => toTime(p));
  const ys = points.map((p) => p.y);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  const dataYMin = Math.min(...ys);
  const dataYMax = Math.max(...ys);

  let yMin = options.yMin ?? dataYMin;
  let yMax = options.yMax ?? dataYMax;
  if (yMin === yMax) {
    yMin -= 1;
    yMax += 1;
  }

  const sx = createScale([xMin, xMax], [plotLeft, plotRight]);
  const sy = createScale([yMin, yMax], [plotBottom, plotTop]);

  const yTickCount = options.yTickCount ?? options.gridLines ?? 4;
  const yTicks = linearTicks(yMin, yMax, yTickCount);
  const xTickCount = options.xTickCount ?? 4;
  const xTickIndices: number[] = [];
  if (points.length === 1) {
    xTickIndices.push(0);
  } else {
    for (let i = 0; i < xTickCount; i++) {
      const idx = Math.round((i * (points.length - 1)) / (xTickCount - 1));
      xTickIndices.push(clamp(idx, 0, points.length - 1));
    }
  }

  const yFormatter = options.yFormatter ?? options.formatY ?? defaultYFormatter;
  const xFormatter =
    options.xFormatter ??
    (options.formatX ? (v: Date | number) => options.formatX!(typeof v === "number" ? v : v.getTime()) : defaultXLabel);
  const spanMs = xMax - xMin;
  const lineColor = options.lineColor ?? options.stroke ?? "var(--accent)";
  const markerColor = options.markerColor ?? "var(--ink)";
  const strokeWidth = options.strokeWidth ?? 2;

  let bandsSvg = "";
  if (options.bands) {
    bandsSvg = options.bands
      .map((b) => {
        const top = clamp(sy(b.max), plotTop, plotBottom);
        const bottom = clamp(sy(b.min), plotTop, plotBottom);
        if (bottom <= top) return "";
        return `<rect x="${plotLeft}" y="${top}" width="${plotW}" height="${bottom - top}" fill="${b.color}" opacity="0.12" />`;
      })
      .join("");
  }

  const gridSvg = yTicks
    .map(
      (v) =>
        `<line x1="${plotLeft}" x2="${plotRight}" y1="${sy(v)}" y2="${sy(v)}" stroke="var(--grid-line)" stroke-width="1" stroke-dasharray="2 2" />`,
    )
    .join("");

  const yLabelsSvg = yTicks
    .map(
      (v) =>
        `<text x="${plotLeft - 6}" y="${sy(v) + 3}" text-anchor="end" ${TEXT_STYLE}>${escapeXml(yFormatter(v))}</text>`,
    )
    .join("");

  const xLabelsSvg = xTickIndices
    .map((idx) => {
      const p = points[idx];
      return `<text x="${sx(toTime(p))}" y="${plotBottom + 14}" text-anchor="middle" ${TEXT_STYLE}>${escapeXml(xFormatter(p.x, spanMs))}</text>`;
    })
    .join("");

  const pathD = linePath(points, sx, sy);
  const areaSvg = options.fill
    ? `<path d="${areaPath(points, sx, sy, plotBottom)}" fill="${options.fill}" opacity="0.12" stroke="none" />`
    : "";
  const last = points[points.length - 1];
  const markerSvg = `<circle cx="${sx(toTime(last))}" cy="${sy(last.y)}" r="5" fill="none" stroke="${lineColor}" stroke-width="2" opacity="0.5" /><circle cx="${sx(toTime(last))}" cy="${sy(last.y)}" r="3" fill="${markerColor}" stroke="var(--canvas)" stroke-width="1.5" />`;

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" role="img" tabindex="0" aria-label="${escapeXml(options.ariaLabel ?? "Line chart")}">
    <title>${escapeXml(options.title ?? "Line chart")}</title>
    ${bandsSvg}
    ${gridSvg}
    <line x1="${plotLeft}" x2="${plotRight}" y1="${plotBottom}" y2="${plotBottom}" stroke="var(--hairline-strong)" stroke-width="1" />
    <line x1="${plotLeft}" x2="${plotLeft}" y1="${plotTop}" y2="${plotBottom}" stroke="var(--hairline-strong)" stroke-width="1" />
    ${areaSvg}
    <path d="${pathD}" fill="none" stroke="${lineColor}" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round" />
    ${markerSvg}
    ${yLabelsSvg}
    ${xLabelsSvg}
  </svg>`;
}

/**
 * Multi-series line chart. Used for max-pain vs spot comparisons.
 */
export function multiLineChart(options: MultiLineChartOptions): string {
  const W = options.width ?? DEFAULT_W;
  const H = options.height ?? DEFAULT_H;
  const M = resolveMargin(options);
  const plotLeft = M.left;
  const plotRight = W - M.right;
  const plotTop = M.top;
  const plotBottom = H - M.bottom;
  const plotW = plotRight - plotLeft;

  const allPoints = options.series.flatMap((s) => s.points);
  if (allPoints.length === 0) {
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${escapeXml(options.ariaLabel ?? "Empty chart")}"><title>${escapeXml(options.title ?? "Chart")}</title><text x="${W / 2}" y="${H / 2}" text-anchor="middle" ${TEXT_STYLE}>No data</text></svg>`;
  }

  const xs = allPoints.map((p) => toTime(p));
  const ys = allPoints.map((p) => p.y);
  const xMin = Math.min(...xs);
  const xMax = Math.max(...xs);
  let yMin = options.yMin ?? Math.min(...ys);
  let yMax = options.yMax ?? Math.max(...ys);
  if (yMin === yMax) {
    yMin -= 1;
    yMax += 1;
  }

  const sx = createScale([xMin, xMax], [plotLeft, plotRight]);
  const sy = createScale([yMin, yMax], [plotBottom, plotTop]);

  const yTickCount = options.yTickCount ?? options.gridLines ?? 4;
  const yTicks = linearTicks(yMin, yMax, yTickCount);
  const xTickCount = options.xTickCount ?? 4;
  const xTickIndices: number[] = [];
  if (allPoints.length === 1) {
    xTickIndices.push(0);
  } else {
    for (let i = 0; i < xTickCount; i++) {
      const idx = Math.round((i * (allPoints.length - 1)) / (xTickCount - 1));
      xTickIndices.push(clamp(idx, 0, allPoints.length - 1));
    }
  }

  const yFormatter = options.yFormatter ?? options.formatY ?? defaultYFormatter;
  const xFormatter =
    options.xFormatter ??
    (options.formatX ? (v: Date | number) => options.formatX!(typeof v === "number" ? v : v.getTime()) : defaultXLabel);
  const spanMs = xMax - xMin;

  const gridSvg = yTicks
    .map(
      (v) =>
        `<line x1="${plotLeft}" x2="${plotRight}" y1="${sy(v)}" y2="${sy(v)}" stroke="var(--grid-line)" stroke-width="1" stroke-dasharray="2 2" />`,
    )
    .join("");

  const yLabelsSvg = yTicks
    .map(
      (v) =>
        `<text x="${plotLeft - 6}" y="${sy(v) + 3}" text-anchor="end" ${TEXT_STYLE}>${escapeXml(yFormatter(v))}</text>`,
    )
    .join("");

  const xLabelsSvg = xTickIndices
    .map((idx) => {
      const p = allPoints[idx];
      return `<text x="${sx(toTime(p))}" y="${plotBottom + 14}" text-anchor="middle" ${TEXT_STYLE}>${escapeXml(xFormatter(p.x, spanMs))}</text>`;
    })
    .join("");

  const seriesSvg = options.series
    .map((s, i) => {
      const pathD = linePath(s.points, sx, sy);
      const dashPreset = s.dashed ? "4 3" : LINE_DASH_PATTERNS[i % LINE_DASH_PATTERNS.length];
      const dash = dashPreset ? ` stroke-dasharray="${dashPreset}"` : "";
      const last = s.points[s.points.length - 1];
      const marker = last
        ? markerShape(MARKER_SHAPES[i % MARKER_SHAPES.length], sx(toTime(last)), sy(last.y), s.color)
        : "";
      return `<path d="${pathD}" fill="none" stroke="${s.color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"${dash} />${marker}`;
    })
    .join("");

  const legendX = plotRight - 4;
  let legendY = plotTop + 4;
  const legendSvg = options.series
    .map((s, i) => {
      const y = legendY + i * 14;
      const dash = s.dashed ? ' stroke-dasharray="3 2"' : "";
      return `<line x1="${legendX - 50}" x2="${legendX - 34}" y1="${y + 5}" y2="${y + 5}" stroke="${s.color}" stroke-width="2"${dash} /><text x="${legendX - 30}" y="${y + 8}" ${TEXT_STYLE}>${escapeXml(s.key)}</text>`;
    })
    .join("");

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" role="img" tabindex="0" aria-label="${escapeXml(options.ariaLabel ?? "Multi-series line chart")}">
    <title>${escapeXml(options.title ?? "Multi-series line chart")}</title>
    ${gridSvg}
    <line x1="${plotLeft}" x2="${plotRight}" y1="${plotBottom}" y2="${plotBottom}" stroke="var(--hairline-strong)" stroke-width="1" />
    <line x1="${plotLeft}" x2="${plotLeft}" y1="${plotTop}" y2="${plotBottom}" stroke="var(--hairline-strong)" stroke-width="1" />
    ${seriesSvg}
    ${legendSvg}
    ${yLabelsSvg}
    ${xLabelsSvg}
  </svg>`;
}

function markerShape(shape: string, x: number, y: number, color: string, size = 3): string {
  const half = size;
  switch (shape) {
    case "square":
      return `<rect x="${x - half}" y="${y - half}" width="${size * 2}" height="${size * 2}" fill="${color}" stroke="var(--canvas)" stroke-width="1.5" />`;
    case "diamond":
      return `<polygon points="${x},${y - half} ${x + half},${y} ${x},${y + half} ${x - half},${y}" fill="${color}" stroke="var(--canvas)" stroke-width="1.5" />`;
    case "triangle":
      return `<polygon points="${x},${y - half} ${x + half},${y + half} ${x - half},${y + half}" fill="${color}" stroke="var(--canvas)" stroke-width="1.5" />`;
    default:
      return `<circle cx="${x}" cy="${y}" r="${size}" fill="${color}" stroke="var(--canvas)" stroke-width="1.5" />`;
  }
}

function regimeLabel(regime: string): string {
  return regime.replace(/_/g, " ").toUpperCase();
}

/**
 * Horizontal regime timeline. Each regime change becomes a colored segment;
 * the most recent (current) regime gets an emphasized border.
 */
export function regimeTimeline(entries: RegimeEntry[], options: RegimeTimelineOptions = {}): string {
  const W = options.width ?? DEFAULT_W;
  const H = options.height ?? 72;
  const colors = { ...DEFAULT_REGIME_COLORS, ...(options.colors ?? {}) };
  const now = options.now ?? new Date();

  if (entries.length === 0) {
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="${escapeXml(options.ariaLabel ?? "Empty regime timeline")}"><title>${escapeXml(options.title ?? "Regime timeline")}</title><text x="${W / 2}" y="${H / 2}" text-anchor="middle" ${TEXT_STYLE}>No regime data</text></svg>`;
  }

  const sorted = [...entries].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  const start = new Date(sorted[0].timestamp).getTime();
  const end = Math.max(now.getTime(), start + 24 * 60 * 60 * 1000);
  const sx = createScale([start, end], [0, W]);

  const barY = 26;
  const barH = 18;

  // Pattern definitions for color-blind accessibility.
  const patternDefs = `
    <defs>
      <pattern id="pattern-up" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
        <rect width="6" height="6" fill="${colors.trending_up ?? "var(--success)"}" />
        <line x1="0" y1="0" x2="0" y2="6" stroke="var(--canvas)" stroke-width="1.5" />
      </pattern>
      <pattern id="pattern-down" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(-45)">
        <rect width="6" height="6" fill="${colors.trending_down ?? "var(--danger)"}" />
        <line x1="0" y1="0" x2="0" y2="6" stroke="var(--canvas)" stroke-width="1.5" />
      </pattern>
      <pattern id="pattern-range" width="4" height="4" patternUnits="userSpaceOnUse">
        <rect width="4" height="4" fill="${colors.range_bound ?? "var(--warning)"}" />
        <circle cx="2" cy="2" r="0.75" fill="var(--canvas)" />
      </pattern>
      <pattern id="pattern-volatile" width="6" height="6" patternUnits="userSpaceOnUse">
        <rect width="6" height="6" fill="${colors.volatile ?? "var(--accent)"}" />
        <line x1="0" y1="3" x2="6" y2="3" stroke="var(--canvas)" stroke-width="1" />
        <line x1="3" y1="0" x2="3" y2="6" stroke="var(--canvas)" stroke-width="1" />
      </pattern>
    </defs>
  `;

  let segmentsSvg = "";
  sorted.forEach((entry, i) => {
    const t0 = new Date(entry.timestamp).getTime();
    const t1 = i < sorted.length - 1 ? new Date(sorted[i + 1].timestamp).getTime() : now.getTime();
    const x = clamp(sx(t0), 0, W);
    const x2 = clamp(sx(t1), 0, W);
    const width = Math.max(1, x2 - x);
    const isCurrent = i === sorted.length - 1;
    const color = colors[entry.regime] ?? "var(--faint)";
    const stroke = isCurrent ? ' stroke="var(--ink)" stroke-width="2"' : "";
    const tsEnd = new Date(t1).toISOString();
    const tsStart = new Date(t0).toISOString();
    segmentsSvg += `<rect x="${x}" y="${barY}" width="${width}" height="${barH}" fill="${color}"${stroke} data-regime="${escapeXml(entry.regime)}" data-start="${escapeXml(tsStart)}" data-end="${escapeXml(tsEnd)}" role="button" tabindex="0" aria-label="${escapeXml(regimeLabel(entry.regime))} from ${tsStart} to ${tsEnd}" style="cursor:pointer" />`;
  });

  const current = sorted[sorted.length - 1];
  const currentLabel = `CURRENT · ${regimeLabel(current.regime)}`;

  const regimes = Array.from(new Set(sorted.map((e) => e.regime)));
  let legendX = 0;
  const legendY = barY + barH + 18;
  const legendSvg = regimes
    .map((r) => {
      const color = colors[r] ?? "var(--faint)";
      const label = regimeLabel(r);
      const swatch = `<rect x="${legendX}" y="${legendY - 7}" width="10" height="10" fill="${color}" />`;
      const text = `<text x="${legendX + 14}" y="${legendY + 2}" ${TEXT_STYLE}>${escapeXml(label)}</text>`;
      legendX += 14 + label.length * 6 + 18;
      return swatch + text;
    })
    .join("");

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" preserveAspectRatio="xMidYMid meet" role="img" tabindex="0" aria-label="${escapeXml(options.ariaLabel ?? "Regime timeline")}">
    <title>${escapeXml(options.title ?? "Regime timeline")}</title>
    ${patternDefs}
    <text x="0" y="14" ${TEXT_STYLE} fill="var(--ink)">${escapeXml(currentLabel)}</text>
    ${segmentsSvg}
    ${legendSvg}
  </svg>`;
}
