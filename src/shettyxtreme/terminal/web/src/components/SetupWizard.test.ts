import { fireEvent, render } from "@testing-library/svelte";
import { expect, test, vi } from "vitest";
import SetupWizard from "./SetupWizard.svelte";

vi.mock("../lib/api", () => ({
  authStatus: vi.fn().mockResolvedValue({ connected: false, has_api_key: false }),
  saveCredentials: vi.fn(),
  saveDirectToken: vi.fn(),
  saveDataToken: vi.fn(),
  savePinTotp: vi.fn(),
  startConsent: vi.fn(),
  testCredentials: vi.fn(),
}));

test("Test and Connect buttons enable once API key and secret are entered", async () => {
  const { getByPlaceholderText, getByText } = render(SetupWizard, { query: null });

  const apiKey = getByPlaceholderText("api_key") as HTMLInputElement;
  const apiSecret = getByPlaceholderText("api_secret") as HTMLInputElement;
  const testBtn = getByText("Test") as HTMLButtonElement;
  const connectBtn = getByText("Connect Dhan") as HTMLButtonElement;

  expect(testBtn.disabled).toBe(true);
  expect(connectBtn.disabled).toBe(true);

  await fireEvent.input(apiKey, { target: { value: "261ce749" } });
  expect(testBtn.disabled).toBe(true);
  expect(connectBtn.disabled).toBe(true);

  await fireEvent.input(apiSecret, { target: { value: "e151be80-73cf-47d8-85d2-ac97ead3a873" } });
  expect(testBtn.disabled).toBe(false);
  expect(connectBtn.disabled).toBe(false);
});
