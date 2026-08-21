import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import PositionsRiskStrip from "./PositionsRiskStrip.svelte";

const mockPositions = [
  {
    symbol: "NIFTY25JAN24000CE",
    exchange: "NSE_FNO",
    quantity: 75,
    net_quantity: 75,
    buy_avg: 120.5,
    m2m: 150.0,
    pnl: 150.0,
    product: "MIS",
    strike: 24000,
    option_type: "CE",
    expiry: "2026-01-30",
    greeks: { delta: 0.5, gamma: 0.01, theta: -10, vega: 2 },
  },
];

const mockRisk = {
  daily_pnl: 150.0,
  margin_used: 50000.0,
  margin_available: 100000.0,
  loss_limit: -5000.0,
  loss_limit_hit: false,
  max_positions: 10,
  active_positions: 1,
};

const mockHistory = [
  {
    symbol: "NIFTY25JAN24000PE",
    entry_price: 100.0,
    exit_price: 110.0,
    quantity: 75,
    realized_pnl: 750.0,
    opened_at: "2026-08-12T10:00:00Z",
    closed_at: "2026-08-12T11:00:00Z",
  },
];

vi.mock("../lib/api", () => ({
  get: vi.fn(),
  closePosition: vi.fn(),
  getPositionHistory: vi.fn(),
}));

vi.mock("../lib/ws", () => ({
  onMessage: vi.fn(() => () => {}),
  isWsConnected: vi.fn(() => false),
}));

vi.mock("svelte-sonner", () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

const { get, closePosition, getPositionHistory } = await import("../lib/api");

describe("PositionsRiskStrip", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(get).mockImplementation((path: string) => {
      if (path === "/api/execution/positions") return Promise.resolve(mockPositions);
      if (path === "/api/execution/risk") return Promise.resolve(mockRisk);
      return Promise.resolve([]);
    });
    vi.mocked(closePosition).mockResolvedValue({ order_id: "C1", status: "FILLED" } as import("../lib/api").OrderRecord);
    vi.mocked(getPositionHistory).mockResolvedValue(mockHistory);
  });

  afterEach(() => {
    cleanup();
  });

  test("renders open positions and close button", async () => {
    const { findByText } = render(PositionsRiskStrip);
    await findByText("NIFTY25JAN24000CE");
    expect(document.body.textContent).toContain("Close");
    expect(document.body.textContent).toContain("150.00");
  });

  test("switching to history tab loads closed positions", async () => {
    const { findByText } = render(PositionsRiskStrip);
    await findByText("NIFTY25JAN24000CE");
    const historyTab = await findByText("History");
    await fireEvent.click(historyTab);
    await waitFor(() => {
      expect(document.body.textContent).toContain("NIFTY25JAN24000PE");
      expect(document.body.textContent).toContain("750.00");
    });
  });

  test("clicking close opens confirmation dialog", async () => {
    const { findByText, findAllByText } = render(PositionsRiskStrip);
    await findByText("NIFTY25JAN24000CE");
    const closeButtons = await findAllByText("Close");
    await fireEvent.click(closeButtons[0]);
    expect(document.body.textContent).toContain("Close position?");
  });
});
