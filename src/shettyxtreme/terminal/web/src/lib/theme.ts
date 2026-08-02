export type Theme = "dark" | "light";

const THEME_KEY = "sx-theme";

function readStored(): Theme | null {
  if (typeof window === "undefined") return null;
  try {
    const v = window.localStorage.getItem(THEME_KEY);
    return v === "light" ? "light" : v === "dark" ? "dark" : null;
  } catch {
    return null;
  }
}

export function getTheme(): Theme {
  return readStored() ?? "dark";
}

export function applyTheme(theme: Theme): void {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* storage unavailable — attribute still applies for this session */
  }
}

export function initTheme(): void {
  applyTheme(getTheme());
}
