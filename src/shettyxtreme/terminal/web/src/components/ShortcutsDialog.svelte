<script lang="ts">
  import { onMount } from "svelte";
  import { Button } from "$lib/components/ui/button";
  import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
  } from "$lib/components/ui/tooltip";
  import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogHeader,
    DialogTitle,
  } from "$lib/components/ui/dialog";
  import { Kbd } from "$lib/components/ui/kbd";
  import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
  } from "$lib/components/ui/table";
  import { Keyboard } from "@lucide/svelte";

  // Single source of truth for the cockpit shortcuts. Keep in sync with the
  // window-level handlers: App.svelte (Ctrl+R), ModeSwitcher.svelte (Ctrl+M),
  // KnowledgePanel.svelte (Ctrl+F), KillSwitch.svelte (Ctrl+Shift+K), and the
  // Ctrl+/ listener at the bottom of this component.
  const SHORTCUTS: { keys: string[]; action: string; detail: string }[] = [
    {
      keys: ["Ctrl", "R"],
      action: "Toggle right dock",
      detail: "Show or hide the logs, proposals, research and knowledge panels.",
    },
    {
      keys: ["Ctrl", "M"],
      action: "Cycle execution mode",
      detail:
        "OBSERVER → PAPER → LIVE → back to OBSERVER. LIVE still asks you to type a confirmation.",
    },
    {
      keys: ["Ctrl", "F"],
      action: "Focus knowledge search",
      detail: "Jump straight to the search box in the knowledge panel.",
    },
    {
      keys: ["Ctrl", "Shift", "K"],
      action: "Toggle kill switch",
      detail: "Stops everything instantly, in any mode, on any screen.",
    },
    {
      keys: ["Ctrl", "/"],
      action: "Toggle this help",
      detail: "Show or hide this shortcut list.",
    },
  ];

  let open = $state(false);

  // Ctrl+/ and Ctrl+? (Shift+/) toggle this dialog — but never hijack while
  // the operator is typing in an input/textarea (same guard as Ctrl+F in
  // KnowledgePanel). Esc closes it via the dialog primitive.
  function onKey(event: KeyboardEvent): void {
    if (!event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key !== "/" && event.key !== "?") return;
    const t = event.target as HTMLElement | null;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
    event.preventDefault();
    open = !open;
  }

  onMount(() => {
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  });
</script>

<Tooltip>
  <TooltipTrigger>
    <Button
      variant="ghost"
      size="icon"
      class="text-muted-foreground hover:text-accent-active"
      onclick={() => (open = true)}
      aria-label="Keyboard shortcuts"
    >
      <Keyboard class="size-4" />
    </Button>
  </TooltipTrigger>
  <TooltipContent>Keyboard shortcuts</TooltipContent>
</Tooltip>

<Dialog open={open} onOpenChange={(o) => !o && (open = false)}>
  <DialogContent class="w-[min(480px,90vw)]">
    <DialogHeader>
      <DialogTitle>Keyboard shortcuts</DialogTitle>
      <DialogDescription>
        These work anywhere in the terminal. Press Ctrl+/ to close.
      </DialogDescription>
    </DialogHeader>
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead class="w-[120px]">Keys</TableHead>
          <TableHead>Action</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {#each SHORTCUTS as sc (sc.action)}
          <TableRow>
            <TableCell>
              <span class="keys">
                {#each sc.keys as key, i (key)}
                  {#if i > 0}
                    <span class="plus" aria-hidden="true">+</span>
                  {/if}
                  <Kbd>{key}</Kbd>
                {/each}
              </span>
            </TableCell>
            <TableCell class="whitespace-normal">
              <span class="action">{sc.action}</span>
              <span class="detail">{sc.detail}</span>
            </TableCell>
          </TableRow>
        {/each}
      </TableBody>
    </Table>
  </DialogContent>
</Dialog>

<style>
  /* Keycap cluster — Kbd keycaps joined by a faint + separator, mono face
     (DESIGN §4 chip; numerals/labels in JetBrains Mono). */
  .keys {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    white-space: nowrap;
  }
  .plus {
    color: var(--faint);
    font-family: var(--font-mono);
    font-size: 10px;
    user-select: none;
  }
  .action {
    display: block;
    color: var(--ink);
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.02em;
  }
  .detail {
    display: block;
    margin-top: 2px;
    color: var(--muted);
    font-size: 11px;
    line-height: 1.5;
  }
</style>
