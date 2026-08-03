import { cleanup, fireEvent, render } from "@testing-library/svelte";
import { afterEach, expect, test, vi } from "vitest";
import SettingsView from "./SettingsView.svelte";

vi.mock("../lib/api", () => ({
  authStatus: vi.fn().mockResolvedValue({
    has_api_key: false,
    has_token: false,
    token_valid: false,
    token_expiry: null,
    connected: false,
    setup_complete: false,
    client_name: null,
    client_id: null,
    data_token_valid: false,
    data_token_expiry: null,
  }),
  logoutAuth: vi.fn(),
  reauth: vi.fn(),
  saveDataToken: vi.fn().mockResolvedValue({ success: true, message: "ok" }),
}));

afterEach(cleanup);

import { saveDataToken } from "../lib/api";

const mockSave = vi.mocked(saveDataToken);

test("Save data token button stays disabled until a token is pasted", async () => {
  const { findByPlaceholderText, findByText } = render(SettingsView);

  const saveBtn = (await findByText("Save data token")) as HTMLButtonElement;
  expect(saveBtn.disabled).toBe(true);

  const field = (await findByPlaceholderText("paste data access token (JWT)")) as HTMLInputElement;
  await fireEvent.input(field, { target: { value: "NIFTY" } });

  const enabledBtn = (await findByText("Save data token")) as HTMLButtonElement;
  expect(enabledBtn.disabled).toBe(false);
});

test("pasting a token and saving calls saveDataToken", async () => {
  const { findByPlaceholderText, findByText } = render(SettingsView);

  const field = (await findByPlaceholderText("paste data access token (JWT)")) as HTMLInputElement;
  await fireEvent.input(field, { target: { value: "  eyJhbGciOiJIUzI1NiJ9.abc  " } });
  await fireEvent.click(await findByText("Save data token"));

  expect(mockSave).toHaveBeenCalledWith("eyJhbGciOiJIUzI1NiJ9.abc");
  expect(field.value).toBe("");
});

test("save failure surfaces the error", async () => {
  mockSave.mockRejectedValueOnce(new Error("boom"));
  const { findByPlaceholderText, findByText } = render(SettingsView);

  const field = (await findByPlaceholderText("paste data access token (JWT)")) as HTMLInputElement;
  await fireEvent.input(field, { target: { value: "eyJhbGciOiJIUzI1NiJ9.abc" } });
  await fireEvent.click(await findByText("Save data token"));

  expect(await findByText("boom")).toBeTruthy();
});
