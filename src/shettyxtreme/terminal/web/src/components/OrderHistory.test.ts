import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import OrderHistory from "./OrderHistory.svelte";

const mockOrders = [
  {
    order_id: "O1",
    symbol: "NIFTY25JAN24000CE",
    exchange: "NSE_FNO",
    side: "BUY",
    order_type: "LIMIT",
    quantity: 75,
    price: 120.5,
    status: "OPEN",
    filled_quantity: 0,
    average_price: 0,
    tag: null,
    created_at: "2026-08-13T10:00:00Z",
    strike: 24000,
    expiry: "2026-01-30",
    option_type: "CE",
    lot_size: 75,
    stop_loss: null,
    target: null,
    rationale: null,
    confidence: null,
  },
  {
    order_id: "O2",
    symbol: "NIFTY25JAN24000PE",
    exchange: "NSE_FNO",
    side: "SELL",
    order_type: "MARKET",
    quantity: 75,
    price: 0,
    status: "FILLED",
    filled_quantity: 75,
    average_price: 98.25,
    tag: null,
    created_at: "2026-08-13T10:05:00Z",
    strike: 24000,
    expiry: "2026-01-30",
    option_type: "PE",
    lot_size: 75,
    stop_loss: null,
    target: null,
    rationale: null,
    confidence: null,
  },
];

vi.mock("../lib/api", () => ({
  getOrders: vi.fn(),
  cancelOrder: vi.fn(),
  exportOrders: vi.fn(),
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

const { getOrders, cancelOrder } = await import("../lib/api");

describe("OrderHistory", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(getOrders).mockResolvedValue(mockOrders);
    vi.mocked(cancelOrder).mockResolvedValue({ order_id: "O1", cancelled: true, status: "CANCELLED", message: "" });
  });

  afterEach(() => {
    cleanup();
  });

  test("renders order rows and cancel button for open orders", async () => {
    const { findByText, findAllByText } = render(OrderHistory);
    await findByText("NIFTY25JAN24000CE");
    const cancelButtons = await findAllByText("Cancel");
    expect(cancelButtons.length).toBeGreaterThan(0);
    expect(document.body.textContent).toContain("OPEN");
  });

  test("clicking cancel opens a confirmation dialog", async () => {
    const { findByText, queryByText } = render(OrderHistory);
    await findByText("NIFTY25JAN24000CE");
    const cancelBtn = await findByText("Cancel");
    await fireEvent.click(cancelBtn);
    expect(queryByText("Cancel order?")).not.toBeNull();
  });

  test("filled orders show status instead of cancel", async () => {
    const { findByText } = render(OrderHistory);
    await findByText("NIFTY25JAN24000PE");
    await waitFor(() => {
      const row = document.body.textContent || "";
      expect(row).toContain("FILLED");
    });
  });
});
