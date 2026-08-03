import { fireEvent, render } from "@testing-library/svelte";
import { expect, test } from "vitest";
import Harness from "./textarea.test-harness.svelte";

test("typing in the native textarea writes back through bind:value", async () => {
  const { getByLabelText, getByTestId } = render(Harness);
  const field = getByLabelText("field") as HTMLTextAreaElement;
  expect(getByTestId("bound").textContent).toBe("");
  await fireEvent.input(field, { target: { value: "NIFTY 24500 CE" } });
  expect(getByTestId("bound").textContent).toBe("NIFTY 24500 CE");
  expect(field.value).toBe("NIFTY 24500 CE");
});
