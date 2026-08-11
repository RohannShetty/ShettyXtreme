<script lang="ts">
  import { onMount } from "svelte";
  import { Toaster as Sonner, type ToasterProps as SonnerProps } from "svelte-sonner";
  import { CircleAlert, CircleCheck, Info, LoaderCircle, TriangleAlert } from "@lucide/svelte";

  type Props = SonnerProps & { class?: string };

  const { class: className, ...rest }: Props = $props();

  // The terminal has no mode-watcher: theme lives on <html data-theme> (theme.ts).
  // Follow it so toasts match the active theme instead of the OS preference.
  let theme: "dark" | "light" = $state("dark");

  onMount(() => {
    const root = document.documentElement;
    const sync = () => {
      theme = root.dataset.theme === "light" ? "light" : "dark";
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { attributes: true, attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  });
</script>

<Sonner
  {theme}
  position="bottom-right"
  offset={16}
  richColors
  closeButton
  class={className}
  style="--normal-bg: var(--surface-overlay); --normal-text: var(--body); --normal-border: var(--hairline-strong); --border-radius: 6px; --toast-width: 360px; --success-bg: var(--surface-overlay); --success-text: var(--success); --success-border: var(--success); --error-bg: var(--surface-overlay); --error-text: var(--danger); --error-border: var(--danger); --warning-bg: var(--surface-overlay); --warning-text: var(--warning); --warning-border: var(--warning); --info-bg: var(--surface-overlay); --info-text: var(--info); --info-border: var(--info);"
  {...rest}
>
  {#snippet loadingIcon()}
    <LoaderCircle class="size-4 text-muted-foreground" />
  {/snippet}
  {#snippet successIcon()}
    <CircleCheck class="size-4 text-success" />
  {/snippet}
  {#snippet errorIcon()}
    <CircleAlert class="size-4 text-danger" />
  {/snippet}
  {#snippet infoIcon()}
    <Info class="size-4 text-info" />
  {/snippet}
  {#snippet warningIcon()}
    <TriangleAlert class="size-4 text-warning" />
  {/snippet}
</Sonner>
