import { cleanup, render } from "@testing-library/svelte";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import RightDockTabs from "./RightDockTabs.svelte";
import { rightDockTab } from "$lib/rightDockTab.svelte";

// All right-dock panels fetch via ../lib/api and subscribe via ../lib/ws;
// mock both so only the tab-selection behavior under test stays real.
vi.mock("../lib/api", () => ({
  get: vi.fn(),
  post: vi.fn(),
  postBody: vi.fn(),
  getOrders: vi.fn(),
  getProposals: vi.fn(),
  approveProposal: vi.fn(),
  rejectProposal: vi.fn(),
  executionMode: vi.fn(),
  riskSummary: vi.fn(),
}));

vi.mock("../lib/ws", () => ({
  onMessage: vi.fn(() => () => {}),
}));

const drawer = (container: HTMLElement) =>
  container.querySelector('[aria-label="Logs drawer"]');

beforeEach(() => {
  vi.clearAllMocks();
  rightDockTab.value = "proposals";
});

afterEach(() => {
  cleanup();
});

test("default render shows the Proposals tab — LogDrawer is not mounted", () => {
  const { container } = render(RightDockTabs);
  expect(container.textContent).toContain("Proposals");
  expect(drawer(container)).toBeNull();
});

test("task 2.3: opening the dock via the header logs button (dockLogsTick bump) lands on the Logs tab", () => {
  const { container } = render(RightDockTabs, { open: true, dockLogsTick: 1 });
  expect(drawer(container)).not.toBeNull();
});

test("opening the dock without a logs-button tick (Ctrl+R / palette sx:open-dock) keeps the current tab", () => {
  const { container } = render(RightDockTabs, { open: true, dockLogsTick: 0 });
  expect(container.textContent).toContain("Proposals");
  expect(drawer(container)).toBeNull();
});
