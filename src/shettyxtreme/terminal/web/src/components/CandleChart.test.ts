import { cleanup, render, waitFor } from "@testing-library/svelte";
import { afterEach, expect, test, vi } from "vitest";
import CandleChart from "./CandleChart.svelte";

vi.mock("../lib/api", () => ({
  getMarketBars: vi.fn(),
}));

afterEach(cleanup);

import { getMarketBars } from "../lib/api";

const mockBars = vi.mocked(getMarketBars);

const threeBars = {
  symbol: "NIFTY",
  exchange: "NSE_FNO",
  bars: [
    { timestamp: "2026-08-03T04:15:00+00:00", open: 24500, high: 24520, low: 24480, close: 24510, volume: 1200 },
    { timestamp: "2026-08-03T04:16:00+00:00", open: 24510, high: 24515, low: 24470, close: 24480, volume: 900 },
    { timestamp: "2026-08-03T04:17:00+00:00", open: 24480, high: 24490, low: 24460, close: 24480, volume: 600 },
  ],
};

test("renders candles with Indian convention colors (red=up, green=down, doji=up)", async () => {
  mockBars.mockResolvedValueOnce(threeBars);
  const { container, findByText } = render(CandleChart);

  await findByText("NIFTY");
  await waitFor(() => {
    const svg = container.querySelector("svg");
    expect(svg).toBeTruthy();
    expect(svg!.querySelectorAll("rect").length).toBeGreaterThanOrEqual(3);
  });

  const svg = container.querySelector("svg")!;
  const bodies = Array.from(svg.querySelectorAll("rect"));
  const upBodies = bodies.filter((r) => r.getAttribute("fill")?.includes("var(--candle-up)"));
  const downBodies = bodies.filter((r) => r.getAttribute("fill")?.includes("var(--candle-down)"));
  expect(upBodies.length).toBe(2); // up candle + doji (close == open counts as up)
  expect(downBodies.length).toBe(1); // down candle

  const wicks = Array.from(svg!.querySelectorAll("line")).filter(
    (l) => l.getAttribute("stroke")?.includes("var(--candle-"),
  );
  expect(wicks.length).toBe(3);
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
