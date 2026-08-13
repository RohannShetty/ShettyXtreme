import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import RiskHeatmap from "./RiskHeatmap.svelte";
import { get } from "../lib/api";
import { onMessage } from "../lib/ws";

vi.mock("../lib/api", () => ({
  get: vi.fn(),
}));

vi.mock("../lib/ws", () => ({
  onMessage: vi.fn(() => () => {}),
}));

vi.mock("./state/EmptyState.svelte", () => ({
  default: vi.fn(({ message }: { message: string }) => message),
}));

vi.mock("./state/LoadingState.svelte", () => ({
  default: vi.fn(({ label }: { label: string }) => label),
}));

vi.mock("./state/ErrorState.svelte", () => ({
  default: vi.fn(({ message }: { message: string }) => message),
}));

const mockGet = vi.mocked(get);
const mockOnMessage = vi.mocked(onMessage);

const heatmapData = {
  sector_exposure: [
    { sector: "BANK", notional: 100000, pnl: -2500, share_pct: 40 },
    { sector: "IT", notional: 80000, pnl: 1500, share_pct: 32 },
  ],
  greeks: {
    delta: { long_val: 0.5, short_val: -0.3, net: 0.2 },
    gamma: { long_val: 0.02, short_val: -0.01, net: 0.01 },
    theta: { long_val: -100, short_val: 80, net: -20 },
    vega: { long_val: 500, short_val: -300, net: 200 },
    lopsided_warning: null,
  },
  stress: {
    scenarios: [
      {
        shift_pct: -5,
        total_pnl: -15000,
        per_position: [
          { symbol: "NIFTY", pnl: -8000 },
          { symbol: "BANKNIFTY", pnl: -7000 },
        ],
      },
      {
        shift_pct: 3,
        total_pnl: 9000,
        per_position: [
          { symbol: "NIFTY", pnl: 5000 },
          { symbol: "BANKNIFTY", pnl: 4000 },
        ],
      },
      { shift_pct: 0, total_pnl: 0 },
    ],
    worst_case_pnl: -15000,
    worst_case_shift: -5,
  },
  margin: {
    margin_used: 50000,
    margin_available: 100000,
    total: 150000,
    utilization_pct: 33.33,
    breach: false,
  },
  position_count: 2,
  enriched_count: 2,
};

beforeEach(() => {
  vi.clearAllMocks();
  mockGet.mockResolvedValue(heatmapData);
});

afterEach(() => {
  cleanup();
});

describe("RiskHeatmap", () => {
  test("renders stress scenarios on load", async () => {
    const { findByText } = render(RiskHeatmap);
    expect(await findByText("STRESS TEST")).toBeTruthy();
    expect(await findByText("-5%")).toBeTruthy();
    expect(await findByText("+3%")).toBeTruthy();
  });

  test("marks the worst-case scenario", async () => {
    const { findByText } = render(RiskHeatmap);
    expect(await findByText("WORST")).toBeTruthy();
  });

  test("per-position P&L breakdown is rendered for scenarios that provide it", async () => {
    const { findAllByText } = render(RiskHeatmap);
    expect((await findAllByText("BANKNIFTY")).length).toBeGreaterThanOrEqual(1);
  });

  test("subscribes to risk WS topic", async () => {
    render(RiskHeatmap);
    await waitFor(() => expect(mockOnMessage).toHaveBeenCalledWith("risk", expect.any(Function)));
  });
});
