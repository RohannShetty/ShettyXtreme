import { fireEvent, render } from "@testing-library/svelte";
import { expect, test } from "vitest";
import Harness from "./table-row.test-harness.svelte";

test("TableRow forwards rest props (data-*, aria-*, event handlers) to the <tr>", async () => {
  const { getByTestId, getByRole } = render(Harness);
  const row = getByTestId("row");
  const tr = row.closest("tr") as HTMLTableRowElement;

  expect(tr).not.toBeNull();
  expect(tr.getAttribute("data-state")).toBe("selected");
  expect(tr.getAttribute("aria-selected")).toBe("true");

  // class merge from the component still applies alongside rest props
  expect(tr.className).toContain("border-b");

  // event handlers in rest props are wired
  expect(getByTestId("keys").textContent).toBe("0");
  await fireEvent.keyDown(tr, { key: "Enter" });
  expect(getByTestId("keys").textContent).toBe("1");

  expect(getByRole("row")).toBe(tr);
});
