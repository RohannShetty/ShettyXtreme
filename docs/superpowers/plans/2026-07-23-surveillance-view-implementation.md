# SurveillanceView Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `SurveillanceView.tsx` with watchlist, scanner list, and mock alert trigger.

**Architecture:** A data-dense table-based view utilizing shadcn/ui components for real-time monitoring of markets and scanner triggered events.

**Tech Stack:** React, Tailwind CSS, shadcn/ui.

## Global Constraints
- No external runtime dependencies (standalone software).
- File size < 500 lines.
- Follow data-dense dashboard style.

---

### Task 1: Scaffolding SurveillanceView
**Files:**
- Create: `terminal/ui/pages/SurveillanceView.tsx`

**Interfaces:**
- Produces: `SurveillanceView` component displaying placeholder grid for Watchlist and Scanners.

- [ ] **Step 1: Write initial component structure**
```tsx
import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function SurveillanceView() {
  return (
    <div className="grid grid-cols-2 gap-4 p-4">
      <Card><CardHeader><CardTitle>Watchlist</CardTitle></CardHeader><CardContent>...</CardContent></Card>
      <Card><CardHeader><CardTitle>Scanners</CardTitle></CardHeader><CardContent>...</CardContent></Card>
    </div>
  );
}
```

- [ ] **Step 2: Commit**
```bash
git add terminal/ui/pages/SurveillanceView.tsx
git commit -m "feat: scaffold surveillance view"
```

### Task 2: Implement Data-Dense Modules & Alert Mechanism
**Files:**
- Modify: `terminal/ui/pages/SurveillanceView.tsx`

**Interfaces:**
- Consumes: `SurveillanceView` scaffolding.

- [ ] **Step 1: Implement Watchlist Module**
```tsx
// Using shadcn Table component
<div className="h-96 overflow-auto">
  <table className="w-full text-xs">
    <thead>...</thead>
    <tbody>{watchlistData.map(row => <tr key={row.symbol}>...</tr>)}</tbody>
  </table>
</div>
```

- [ ] **Step 2: Implement Scanner List & Mock Alert**
```tsx
const triggerAlert = (symbol: string) => { console.log(`Alert triggered for ${symbol}`); };
// Mock scanners mapping
{scanners.map(s => 
  <div key={s.id} className="flex justify-between p-2 border-b cursor-pointer" onClick={() => triggerAlert(s.symbol)}>
    <span>{s.symbol}</span>
    <span className="text-red-500">ALERT</span>
  </div>
)}
```

- [ ] **Step 3: Commit**
```bash
git add terminal/ui/pages/SurveillanceView.tsx
git commit -m "feat: add watchlist and scanner alert functionality"
```
