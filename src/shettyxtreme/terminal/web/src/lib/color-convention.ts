export type ColorConvention = "indian" | "international";

const CONVENTION_KEY = "sx-convention";

function readStored(): ColorConvention | null {
  if (typeof window === "undefined") return null;
  try {
    const v = window.localStorage.getItem(CONVENTION_KEY);
    return v === "indian" ? "indian" : v === "international" ? "international" : null;
  } catch {
    return null;
  }
}

export function getColorConvention(): ColorConvention {
  return readStored() ?? "international";
}

export function applyColorConvention(convention: ColorConvention): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.convention = convention;
  try {
    window.localStorage.setItem(CONVENTION_KEY, convention);
  } catch {
    /* storage unavailable — attribute still applies for this session */
  }
}

export function initColorConvention(): void {
  applyColorConvention(getColorConvention());
}
