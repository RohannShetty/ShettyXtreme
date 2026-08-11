import { fireEvent, render } from "@testing-library/svelte";
import { expect, test, vi } from "vitest";
import SetupWizard from "./SetupWizard.svelte";

vi.mock("../lib/api", () => ({
  authStatus: vi.fn().mockResolvedValue({ connected: false, has_api_key: false }),
  saveCredentials: vi.fn(),
  startAuth: vi.fn(),
  testCredentials: vi.fn(),
}));

test("Test and Connect buttons enable once App ID and Secret ID are entered", async () => {
  const { getByPlaceholderText, getByText } = render(SetupWizard, { query: null });

  const appId = getByPlaceholderText("APP_ID") as HTMLInputElement;
  const secretId = getByPlaceholderText("secret_id") as HTMLInputElement;
  const testBtn = getByText("Test") as HTMLButtonElement;
  const connectBtn = getByText("Connect Fyers") as HTMLButtonElement;

  expect(testBtn.disabled).toBe(true);
  expect(connectBtn.disabled).toBe(true);

  await fireEvent.input(appId, { target: { value: "ABCDEFGHIJ" } });
  expect(testBtn.disabled).toBe(true);
  expect(connectBtn.disabled).toBe(true);

  await fireEvent.input(secretId, { target: { value: "e151be80-73cf-47d8-85d2-ac97ead3a873" } });
  expect(testBtn.disabled).toBe(false);
  expect(connectBtn.disabled).toBe(false);
});
