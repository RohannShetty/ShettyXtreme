import { fireEvent, render } from "@testing-library/svelte";
import { expect, test } from "vitest";
import Harness from "./input.test-harness.svelte";

test("typing in the native input writes back through bind:value", async () => {
  const { getByLabelText, getByTestId } = render(Harness);
  const field = getByLabelText("field") as HTMLInputElement;
  expect(getByTestId("bound").textContent).toBe("");
  await fireEvent.input(field, { target: { value: "NIFTY" } });
  expect(getByTestId("bound").textContent).toBe("NIFTY");
  expect(field.value).toBe("NIFTY");
});
