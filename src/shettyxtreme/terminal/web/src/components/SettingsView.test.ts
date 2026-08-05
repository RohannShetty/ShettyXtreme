import { cleanup, fireEvent, render } from "@testing-library/svelte";
import { afterEach, expect, test, vi } from "vitest";
import SettingsView from "./SettingsView.svelte";

vi.mock("../lib/api", () => ({
  authStatus: vi.fn().mockResolvedValue({
    broker: "fyers",
    has_api_key: true,
    has_token: false,
    token_valid: false,
    token_expiry: null,
    connected: false,
    setup_complete: false,
    client_name: null,
    client_id: null,
  }),
  logoutAuth: vi.fn(),
  reauth: vi.fn(),
}));

afterEach(cleanup);

import { authStatus, reauth } from "../lib/api";

const mockReauth = vi.mocked(reauth);
const mockAuth = vi.mocked(authStatus);

test("shows the broker row as fyers", async () => {
  const { findByText } = render(SettingsView);
  expect(await findByText("fyers")).toBeTruthy();
});

test("Re-auth button triggers the Fyers auth start", async () => {
  mockReauth.mockResolvedValue({
    login_url: "https://api-t1.fyers.in/api/v3/generate-authcode?client_id=APP123",
    state: "state123",
  });
  const { findByText } = render(SettingsView);

  const btn = (await findByText("Re-auth (open Fyers login)")) as HTMLButtonElement;
  await fireEvent.click(btn);

  expect(mockReauth).toHaveBeenCalledTimes(1);
});

test("Logout clears the session and reloads status", async () => {
  mockAuth.mockClear();
  const { findByText } = render(SettingsView);

  const btn = (await findByText("Logout")) as HTMLButtonElement;
  await fireEvent.click(btn);

  expect(mockAuth).toHaveBeenCalledTimes(2); // initial onMount load + post-logout reload
});
