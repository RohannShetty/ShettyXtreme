# Cockpit Design: Workflow-Prioritized Data-Dense Terminal

## Overview
A web-based trading dashboard prioritizing situational awareness. Instead of a single crowded view, the UI uses **Workflow-Prioritized Views** that toggle the dominant cockpit state based on whether the operator is in `Research/Observation` mode or `Execution` mode.

## Core Components
- **Top Bar (Global Status)**: Persistent Market Status, Broker Connection (Dhan), System Health, Risk Budget Health.
- **Workflow Controller**: Tabs for switching between `Market Surveillance` (Scanners) and `Execution Cockpit`.

### 1. Market Surveillance View (Observation)
- **Primary Panel**: Data-heavy watchlists, market internals (ADR), and active scanner alerts.
- **Secondary**: Quick-glance signals (conviction score, regime).

### 2. Execution Cockpit (Active Trading)
- **Primary Panel**: Active Position Management (TP/TSL controls), Order Queue.
- **Secondary**: Live risk monitoring, immediate trade execution module.

## Navigation & Controls
- Workflow switching handled by a clean tab system at the top.
- Data-dense design using small, clear fonts and high-contrast indicators from the `Data-Dense Dashboard` palette.

## UX Principles
- **Visual Priority**: Urgent alerts (Scanner/Risk breach) trigger tray pop-ins regardless of the current view.
- **Cognitive Load Reduction**: Only show what is actionable for the chosen workflow mode.
