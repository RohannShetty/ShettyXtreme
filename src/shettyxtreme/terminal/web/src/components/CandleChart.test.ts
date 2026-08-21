import { cleanup, render, waitFor } from "@testing-library/svelte";
import { afterEach, expect, test, vi } from "vitest";
import CandleChart from "./CandleChart.svelte";

vi.mock("../lib/api", () => ({
  getMarketBars: vi.fn(),
}));

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  mockBars.mockReset();
});

import { getMarketBars, type MarketBarsResponse } from "../lib/api";

const mockBars = vi.mocked(getMarketBars);

const threeBars = {
  symbol: "NIFTY",
  exchange: "NSE_FNO",
  bars: [
    { timestamp: "2026-08-03T04:15:00+00:00", open: 24500, high: 24520, low: 24480, close: 24510, volume: 1200 },
    { timestamp: "2026-08-03T04:16:00+00:00", open: 24500, high: 24515, low: 24470, close: 24480, volume: 900 },
    { timestamp: "2026-08-03T04:17:00+00:00", open: 24480, high: 24490, low: 24460, close: 24480, volume: 600 },
  ],
};

function bars(n: number) {
  return Array.from({ length: n }, (_, i) => ({
    timestamp: `2026-08-03T00:00:${String(i).padStart(3, "0")}Z`,
    open: 24500,
    high: 24520,
    low: 24480,
    close: 24510,
    volume: 1000,
  }));
}

test("renders candles with convention-driven colors (up/down tokens, doji=up)", async () => {
  mockBars.mockResolvedValueOnce(threeBars);
  const { container, findByText } = render(CandleChart);

  await findByText("NIFTY");
  await waitFor(() => {
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
    expect(svg!.querySelectorAll("rect").length).toBeGreaterThanOrEqual(3);
  });

  const svg = container.querySelector("svg")!;
  const bodies = Array.from(svg.querySelectorAll("rect.candle-body"));
  const upBodies = bodies.filter((r) => r.getAttribute("fill") === "var(--candle-up)");
  const downBodies = bodies.filter((r) => r.getAttribute("fill") === "var(--candle-down)");
  expect(upBodies.length).toBe(2); // up candle + doji (close == open counts as up)
  expect(downBodies.length).toBe(1); // down candle

  const wicks = Array.from(svg!.querySelectorAll("line")).filter(
    (l) => l.getAttribute("stroke")?.includes("var(--candle-"),
  );
  expect(wicks.length).toBe(3);
});

test("scale: up-candle body sits above down-candle body (higher price = smaller y)", async () => {
  mockBars.mockResolvedValueOnce(threeBars);
  const { container, findByText } = render(CandleChart);

  await findByText("NIFTY");
  await waitFor(() => {
    expect(container.querySelectorAll("rect.candle-body").length).toBe(3);
  });

  const bodies = Array.from(container.querySelectorAll("rect.candle-body"));
  const up = bodies.find((r) => r.getAttribute("fill") === "var(--candle-up)");
  const down = bodies.find((r) => r.getAttribute("fill") === "var(--candle-down)");
  expect(up).toBeTruthy();
  expect(down).toBeTruthy();
  expect(Number(up!.getAttribute("y"))).toBeLessThan(Number(down!.getAttribute("y")));
});

test("scale: caps rendered bars at 90 when the feed exceeds it", async () => {
  mockBars.mockResolvedValueOnce({ symbol: "NIFTY", exchange: "NSE_FNO", bars: bars(120) });
  const { container, findByText } = render(CandleChart);

  await findByText("NIFTY");
  await waitFor(() => {
    expect(container.querySelectorAll("rect.candle-body").length).toBeGreaterThan(0);
  });
  expect(container.querySelectorAll("rect.candle-body").length).toBeLessThanOrEqual(90);
});

test("shows a loading note while the bars request is pending", async () => {
  vi.useFakeTimers();
  mockBars.mockImplementationOnce(() => new Promise<never>(() => {}));
  const { container } = render(CandleChart);

  await vi.advanceTimersByTimeAsync(250);
  expect(container.textContent).toContain("Loading");
});

test("debounces refetch and drops stale responses from an earlier symbol", async () => {
  vi.useFakeTimers();
  let resolveOld!: (v: MarketBarsResponse) => void;
  let resolveNew!: (v: MarketBarsResponse) => void;
  mockBars
    .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }))
    .mockImplementationOnce(() => new Promise((resolve) => { resolveNew = resolve; }));

  const oldPayload = { symbol: "OLD", exchange: "NSE_FNO", bars: bars(3) };
  const newPayload = { symbol: "NEW", exchange: "NSE_FNO", bars: bars(2) };

  const { container, rerender } = render(CandleChart, { props: { symbol: "OLD" } });
  await vi.advanceTimersByTimeAsync(250);
  expect(mockBars).toHaveBeenCalledTimes(1);

  await rerender({ symbol: "NEW" });
  expect(mockBars).toHaveBeenCalledTimes(1); // debounced — no refetch yet
  await vi.advanceTimersByTimeAsync(250);
  expect(mockBars).toHaveBeenCalledTimes(2);

  resolveNew!(newPayload);
  await vi.advanceTimersByTimeAsync(0);
  expect(container.querySelectorAll("rect.candle-body").length).toBe(2);

  resolveOld!(oldPayload);
  await vi.advanceTimersByTimeAsync(0);
  expect(container.querySelectorAll("rect.candle-body").length).toBe(2); // stale dropped
});

test("shows error text when the bars request fails", async () => {
  mockBars.mockRejectedValueOnce(new Error("boom"));
  const { findByText } = render(CandleChart);

  expect(await findByText("boom")).toBeTruthy();
});

test("shows muted empty state when no bars are returned", async () => {
  mockBars.mockResolvedValueOnce({ symbol: "NIFTY", exchange: "NSE_FNO", bars: [] });
  const { findByText } = render(CandleChart);

  expect(await findByText("No chart data.")).toBeTruthy();
});
