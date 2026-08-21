import { describe, expect, test, beforeEach } from "vitest";
import {
  getColorConvention,
  applyColorConvention,
  initColorConvention,
  type ColorConvention,
} from "./color-convention";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.removeAttribute("data-convention");
});

describe("getColorConvention", () => {
  test("defaults to international when localStorage is empty", () => {
    expect(getColorConvention()).toBe("international");
  });

  test("returns indian when stored", () => {
    window.localStorage.setItem("sx-convention", "indian");
    expect(getColorConvention()).toBe("indian");
  });

  test("returns international when stored", () => {
    window.localStorage.setItem("sx-convention", "international");
    expect(getColorConvention()).toBe("international");
  });

  test("falls back to international for invalid stored value", () => {
    window.localStorage.setItem("sx-convention", "murican");
    expect(getColorConvention()).toBe("international");
  });
});

describe("applyColorConvention", () => {
  test("sets data-convention attribute on <html>", () => {
    applyColorConvention("indian");
    expect(document.documentElement.dataset.convention).toBe("indian");
  });

  test("persists to localStorage", () => {
    applyColorConvention("international");
    expect(window.localStorage.getItem("sx-convention")).toBe("international");
  });

  test("round-trips through localStorage", () => {
    applyColorConvention("indian");
    expect(getColorConvention()).toBe("indian");
    applyColorConvention("international");
    expect(getColorConvention()).toBe("international");
  });
});

describe("initColorConvention", () => {
  test("applies international by default", () => {
    initColorConvention();
    expect(document.documentElement.dataset.convention).toBe("international");
  });

  test("applies stored value", () => {
    window.localStorage.setItem("sx-convention", "indian");
    initColorConvention();
    expect(document.documentElement.dataset.convention).toBe("indian");
  });
});
