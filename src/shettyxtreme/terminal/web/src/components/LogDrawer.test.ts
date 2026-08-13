import { cleanup, render } from "@testing-library/svelte";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import LogDrawer from "./LogDrawer.svelte";

vi.mock("../lib/api", () => ({
  get: vi.fn(),
}));

vi.mock("../lib/ws", () => ({
  onMessage: vi.fn(() => () => {}),
}));

import { get } from "../lib/api";
import type { Mock } from "vitest";

const mockGet = get as Mock;

beforeEach(() => {
  mockGet.mockReset();
  mockGet.mockResolvedValue([]);
});

afterEach(() => {
  cleanup();
});

test("task 2.3: the panel renders its content even when the dock state `open` is false — a direct Logs-tab click can never land on a blank panel", () => {
  const { container } = render(LogDrawer, { open: false });
  const aside = container.querySelector('[aria-label="Logs drawer"]');
  expect(aside).not.toBeNull();
  // The old `.drawer:not(.open) { display: none }` gating is gone — the aside
  // carries no `open` class and its content is in the DOM.
  expect(aside!.className).not.toContain("open");
  expect(container.textContent).toContain("No log entries yet.");
});
