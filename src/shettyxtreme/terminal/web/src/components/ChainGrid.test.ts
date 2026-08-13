import { cleanup, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import ChainGrid from "./ChainGrid.svelte";

// Captured WS "tick" handlers (the mock registers via onMessage) so tests can
// drive the live payload stream exactly as ws_manager would deliver it.
const { mockHandlers } = vi.hoisted(() => ({
  mockHandlers: new Map<string, (data: unknown) => void>(),
}));

vi.mock("../lib/api", () => ({
  get: vi.fn(),
  getMarketBars: vi.fn(),
}));

vi.mock("../lib/ws", () => ({
  onMessage: vi.fn((topic: string, handler: (data: unknown) => void) => {
    mockHandlers.set(topic, handler);
    return () => {
      mockHandlers.delete(topic);
    };
  }),
}));

vi.mock("../lib/selection", () => ({
  selectedSymbol: { subscribe: vi.fn(() => () => {}) },
}));

import { get, getMarketBars } from "../lib/api";
import type { Mock } from "vitest";

type Contract = {
  strike: number;
  option_type: string;
  ltp: number;
  iv: number;
  delta: number;
  gamma: number;
  theta: number;
  vega: number;
  oi: number;
  volume: number;
  bid: number;
  ask: number;
};

type OptionsResponse = { underlying: string; expiry: string; contracts: Contract[] };

const mockGet = get as Mock<(path: string) => Promise<OptionsResponse>>;
const mockBars = vi.mocked(getMarketBars);

const chainPayload: OptionsResponse = {
  underlying: "NIFTY",
  expiry: "",
  contracts: [
    { strike: 25000, option_type: "CE", ltp: 240.5, iv: 12.3, delta: 0.55, gamma: 0.0001, theta: -2.0, vega: 1.5, oi: 100, volume: 500, bid: 240.0, ask: 241.0 },
    { strike: 25000, option_type: "PE", ltp: 180.25, iv: 13.1, delta: -0.45, gamma: 0.0001, theta: -1.8, vega: 1.4, oi: 200, volume: 300, bid: 180.0, ask: 181.0 },
    { strike: 25100, option_type: "CE", ltp: 90.75, iv: 14.0, delta: 0.4, gamma: 0.0002, theta: -1.2, vega: 1.1, oi: 50, volume: 100, bid: 90.5, ask: 91.0 },
  ],
};

beforeEach(() => {
  mockGet.mockReset();
  mockBars.mockReset();
  mockGet.mockResolvedValue(chainPayload);
  mockBars.mockResolvedValue({ symbol: "NIFTY", exchange: "NSE_FNO", bars: [] });
  mockHandlers.clear();
});

afterEach(() => {
  cleanup();
});

async function renderLoaded() {
  const { container } = render(ChainGrid);
  await waitFor(() => {
    expect(container.querySelector('[data-strike="25000"]')).toBeTruthy();
  });
  return container;
}

test("live tick updates LTP and OI via strike/option_type from the wire payload", async () => {
  const container = await renderLoaded();
  expect(container.textContent).toContain("240.50"); // loaded CE 25000 LTP

  const handler = mockHandlers.get("tick");
  expect(handler).toBeTruthy();
  handler!({
    symbol: "NIFTY",
    ltp: 248.0,
    change_pct: 3.1,
    volume: 999,
    oi: 123456,
    strike: 25000,
    option_type: "CE",
  });

  await waitFor(() => {
    expect(container.textContent).toContain("248.00");
    expect(container.textContent).toMatch(/1[,\s\u00a0]?23[,\s\u00a0]?456/);
  });
});

test("tick without chain fields (index/equity symbol) is ignored — no symbol regex fallback", async () => {
  const container = await renderLoaded();

  const handler = mockHandlers.get("tick");
  expect(handler).toBeTruthy();
  handler!({
    symbol: "NIFTY",
    ltp: 9999.0,
    change_pct: 0.1,
    volume: 1,
    oi: null,
    strike: null,
    option_type: null,
  });

  // The loaded LTP must be untouched and the phantom 9999.00 must never appear.
  expect(container.textContent).toContain("240.50");
  expect(container.textContent).not.toContain("9999.00");
});

test("live tick also updates the OI column from the payload oi field", async () => {
  const container = await renderLoaded();

  const handler = mockHandlers.get("tick");
  expect(handler).toBeTruthy();
  handler!({
    symbol: "NIFTY",
    ltp: 241.0,
    change_pct: 0.4,
    volume: 501,
    oi: 777777,
    strike: 25000,
    option_type: "PE",
  });

  await waitFor(() => {
    expect(container.textContent).toMatch(/7[,\s\u00a0]?77[,\s\u00a0]?777/);
  });
});

test("greeks columns (Δ/Γ/Θ/V) render for CE and PE sides", async () => {
  const container = await renderLoaded();

  // Delta values from the fixture: CE 25000 delta=0.55, PE 25000 delta=-0.45
  // fmtGreek uses en-IN locale with 2 decimal places for delta
  await waitFor(() => {
    const text = container.textContent ?? "";
    // CE delta 0.55
    expect(text).toContain("0.55");
    // PE delta -0.45
    expect(text).toContain("-0.45");
    // Theta values: CE theta=-2.0, PE theta=-1.8
    expect(text).toContain("-2.00");
    expect(text).toContain("-1.80");
    // Vega values: CE vega=1.5, PE vega=1.4
    expect(text).toContain("1.50");
    expect(text).toContain("1.40");
  });
});

test("greeks column headers render Δ/Γ/Θ/V labels", async () => {
  const container = await renderLoaded();

  await waitFor(() => {
    const text = container.textContent ?? "";
    // Greek letter labels appear in the header
    expect(text).toContain("Δ");
    expect(text).toContain("Γ");
    expect(text).toContain("Θ");
  });
});
