/**
 * Reactive debounce helper for Svelte 5 runes.
 *
 * Returns an object whose `current` property reflects `source` after
 * `delay` ms of stability. Reading `current` inside a template or
 * `$derived` keeps it reactive.
 *
 * Use this to throttle chart re-renders on rapid data updates
 * (e.g. WebSocket ticks) without dropping the latest value.
 */
export function useDebounce<T>(source: () => T, delay = 500): { readonly current: T } {
  let value = $state(source());
  let timeout: ReturnType<typeof setTimeout>;

  $effect(() => {
    const next = source();
    clearTimeout(timeout);
    timeout = setTimeout(() => {
      value = next;
    }, delay);
    return () => clearTimeout(timeout);
  });

  return {
    get current() {
      return value;
    },
  };
}

/**
 * One-shot debounce for callback functions.
 */
export function debounce<T extends (...args: Parameters<T>) => ReturnType<T>>(
  fn: T,
  delay = 500,
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout>;
  return (...args) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), delay);
  };
}
