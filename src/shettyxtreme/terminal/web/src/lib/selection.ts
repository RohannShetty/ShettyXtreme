import { writable } from "svelte/store";

/**
 * Selected instrument — the symbol plus the exchange it lives on.
 *
 * Carrying the exchange alongside the symbol lets consumers (header hero,
 * chain grid) read it directly instead of deriving it from a watchlist REST
 * call or a hardcoded default. Consumers should fall back to their domain
 * default when `exchange` is empty (Header → "NSE", ChainGrid → "NSE_FNO")
 * so a legacy string-only setter degrades gracefully.
 */
export type SelectedSymbol = {
  symbol: string;
  exchange: string;
};

export const selectedSymbol = writable<SelectedSymbol>({
  symbol: "",
  exchange: "",
});
