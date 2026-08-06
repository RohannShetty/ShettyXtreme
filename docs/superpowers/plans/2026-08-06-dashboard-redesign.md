# Dashboard Redesign Plan — 2026-08-06

## Problem
- Frames overlapping in right dock (ProposalQueue, ResearchPanel, KnowledgePanel, LogDrawer stacked without proper sizing)
- Generic Bloomberg-terminal look
- User wants modern, unique design

## Solution: "Command Center" Layout

### New Grid Structure
```
.app-grid {
  display: grid;
  grid-template-columns: 1fr;
  grid-template-rows: 
    auto        /* header */
    auto        /* ticker strip */
    minmax(0, 1fr)  /* main workspace */
    auto;       /* positions strip */
}
```

### Workspace: 3-Column with Proper Sizing
```
.workspace {
  display: grid;
  grid-template-columns: 
    var(--rail-w, 280px)   /* watchlist */
    8px                     /* gutter */
    minmax(0, 1fr)          /* center (flexible) */
    8px                     /* gutter */
    var(--right-w, 360px);  /* right dock */
}
```

### Right Dock: Tabbed Interface (Fixes Overlapping)
Instead of stacking all panels, use tabs:
- **Proposals** tab: ProposalQueue
- **Research** tab: ResearchPanel + KnowledgePanel
- **Logs** tab: LogDrawer

This eliminates the overlapping issue entirely.

### Modern Design Elements
1. **Subtle depth**: Use `box-shadow: 0 1px 3px rgba(0,0,0,0.4)` on panels (exception to no-shadow rule for modern feel)
2. **Rounded corners**: Increase from 6px to 8px on panels
3. **Gradient accents**: Subtle gradient on header (amber to orange)
4. **Glassmorphism**: Semi-transparent panels with backdrop-filter blur (opt-in, respects DESIGN.md)
5. **Animated transitions**: Smooth panel transitions

### Component Changes
- **Header**: Gradient background, larger logo, modern typography
- **Watchlist**: Card-style rows with hover effects
- **Center tabs**: Pill-style tabs instead of underline
- **Right dock**: Tabbed interface with icons
- **Positions strip**: Compact card layout

### Migration Path
1. Update App.svelte grid structure
2. Create RightDockTabs component
3. Update CSS variables for new sizing
4. Add modern design tokens
5. Test responsive behavior

## Files to Modify
- `src/shettyxtreme/terminal/web/src/App.svelte` — main layout
- `src/shettyxtreme/terminal/web/src/components/RightDockTabs.svelte` — new component
- `DESIGN.md` — add modern design tokens (optional)
