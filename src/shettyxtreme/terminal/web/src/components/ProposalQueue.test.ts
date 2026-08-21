import { cleanup, fireEvent, render, waitFor } from "@testing-library/svelte";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import ProposalQueue from "./ProposalQueue.svelte";
import {
  approveProposal,
  executionMode,
  getProposals,
  rejectProposal,
  riskSummary,
} from "../lib/api";
import { onMessage } from "../lib/ws";
import { toast } from "svelte-sonner";

vi.mock("../lib/api", () => ({
  getProposals: vi.fn(),
  executionMode: vi.fn(),
  riskSummary: vi.fn(),
  approveProposal: vi.fn(),
  rejectProposal: vi.fn(),
}));

let proposalHandler: ((data: unknown) => void) | null = null;

vi.mock("../lib/ws", () => ({
  onMessage: vi.fn((topic: string, handler: (data: unknown) => void) => {
    if (topic === "proposal") proposalHandler = handler;
    return () => { proposalHandler = null; };
  }),
}));

vi.mock("svelte-sonner", () => ({
  toast: {
    success: vi.fn(),
    info: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
  },
}));

const mockGetProposals = vi.mocked(getProposals);
const mockExecutionMode = vi.mocked(executionMode);
const mockRiskSummary = vi.mocked(riskSummary);
const mockApprove = vi.mocked(approveProposal);
const mockReject = vi.mocked(rejectProposal);
const mockOnMessage = vi.mocked(onMessage);
const mockToast = vi.mocked(toast);

const pendingProposal = {
  id: "p1",
  symbol: "NIFTY",
  exchange: "NSE_FNO",
  side: "BUY",
  quantity: 50,
  price: null,
  order_type: "MKT",
  product: "MIS",
  conviction: 0.6,
  D: 1,
  P: 2,
  G: "G1",
  source: "test",
  hint_kind: "chain",
  signal_id: "s1",
  status: "PENDING",
  reason: "",
  timestamp: new Date().toISOString(),
  strike: 24000,
  expiry: "2026-08-27",
  option_type: "CE",
  lot_size: 50,
  lots: 1,
  entry_premium: 100,
  stop_loss: null,
  target: null,
  rationale: "test rationale",
  confidence: 0.7,
  ev_after_cost: 500,
  strategy: "long-call",
  underlying: "NIFTY",
};

beforeEach(() => {
  vi.clearAllMocks();
  proposalHandler = null;
  mockExecutionMode.mockResolvedValue({ mode: "PAPER", csrf_token: "token" });
  mockRiskSummary.mockResolvedValue({
    daily_pnl: 0,
    margin_used: 0,
    margin_available: 100000,
    loss_limit: -5000,
    loss_limit_hit: false,
    max_positions: 10,
    active_positions: 0,
  });
  mockGetProposals.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
});

describe("ProposalQueue active tab", () => {
  test("renders pending proposals fetched on mount", async () => {
    mockGetProposals.mockResolvedValue([pendingProposal]);
    const { findByText } = render(ProposalQueue);
    expect(await findByText("NIFTY")).toBeTruthy();
    expect(mockGetProposals).toHaveBeenCalledWith({ status: "PENDING" });
  });

  test("does not poll — onMount fetches once and subscribes to WS", async () => {
    mockGetProposals.mockResolvedValue([]);
    render(ProposalQueue);
    await waitFor(() => expect(mockGetProposals).toHaveBeenCalledTimes(1));
    expect(mockOnMessage).toHaveBeenCalledWith("proposal", expect.any(Function));
  });

  test("WS 'created' event prepends a pending proposal and toasts", async () => {
    mockGetProposals.mockResolvedValue([]);
    const { findByText } = render(ProposalQueue);
    await findByText("No pending proposals.");
    const created = { ...pendingProposal, id: "p2" };
    proposalHandler!({ action: "created", proposal: created });
    expect(await findByText("NIFTY")).toBeTruthy();
    expect(mockToast.info).toHaveBeenCalledWith("New proposal: BUY NIFTY", {
      description: "test rationale",
    });
  });

  test("WS 'approved' event removes the proposal and toasts success", async () => {
    mockGetProposals.mockResolvedValue([pendingProposal]);
    const { findByText, queryByText } = render(ProposalQueue);
    await findByText("NIFTY");
    proposalHandler!({ action: "approved", proposal: { ...pendingProposal, status: "APPROVED" } });
    await waitFor(() => expect(queryByText("APPROVE")).toBeNull());
    expect(mockToast.success).toHaveBeenCalledWith("Proposal approved: BUY NIFTY", {
      description: "1 lot (50 qty) → APPROVED",
    });
  });

  test("WS 'rejected' event removes the proposal and toasts error", async () => {
    mockGetProposals.mockResolvedValue([pendingProposal]);
    const { findByText, queryByText } = render(ProposalQueue);
    await findByText("NIFTY");
    proposalHandler!({
      action: "rejected",
      proposal: { ...pendingProposal, status: "REJECTED", reason: "risk breach" },
    });
    await waitFor(() => expect(queryByText("APPROVE")).toBeNull());
    expect(mockToast.error).toHaveBeenCalledWith("Proposal rejected: BUY NIFTY", {
      description: "risk breach",
    });
  });

  test("approve button opens confirm dialog", async () => {
    mockGetProposals.mockResolvedValue([pendingProposal]);
    const { findByText } = render(ProposalQueue);
    const approveBtn = await findByText("APPROVE");
    await fireEvent.click(approveBtn);
    expect(await findByText("Confirm order")).toBeTruthy();
  });
});

describe("ProposalQueue history tab", () => {
  test("clicking History tab fetches closed proposals", async () => {
    const closed = { ...pendingProposal, id: "h1", status: "REJECTED", reason: "expired" };
    mockGetProposals.mockImplementation((query) => {
      if (query?.status === "PENDING") return Promise.resolve([]);
      return Promise.resolve([closed]);
    });
    const { findByText } = render(ProposalQueue);
    const historyTab = await findByText("History");
    await fireEvent.click(historyTab);
    await waitFor(() =>
      expect(mockGetProposals).toHaveBeenCalledWith({
        status: ["APPROVED", "REJECTED", "EXPIRED"],
        start: undefined,
        end: undefined,
      })
    );
    expect(await findByText("REJECTED")).toBeTruthy();
  });

  test("date range filters are passed to getProposals", async () => {
    mockGetProposals.mockResolvedValue([]);
    const { findByText, container } = render(ProposalQueue);
    await fireEvent.click(await findByText("History"));
    const inputs = container.querySelectorAll('input[type="date"]');
    await fireEvent.input(inputs[0], { target: { value: "2026-08-01" } });
    await fireEvent.input(inputs[1], { target: { value: "2026-08-31" } });
    await fireEvent.click(await findByText("Apply"));
    await waitFor(() =>
      expect(mockGetProposals).toHaveBeenCalledWith({
        status: ["APPROVED", "REJECTED", "EXPIRED"],
        start: "2026-08-01",
        end: "2026-08-31",
      })
    );
  });
});
