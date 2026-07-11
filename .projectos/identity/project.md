---
project_id: "proj_shettyxtreme_001"
name: "ShettyXtreme"
description: "Unified Indian-market trading intelligence and execution platform — combining terminal-grade market exploration, research, analytics, live decision support, options strategy intelligence, and broker-integrated execution."
type: "platform"
primary_language: "python"
primary_framework: null
repository_url: "https://github.com/RohannShetty/ShettyXtreme"
governed_since: "2026-07-12T00:00:00Z"
last_identity_review: "2026-07-12T00:00:00Z"
architects: ["Rohan Shetty"]
---

# ShettyXtreme

## What It Is

ShettyXtreme is a trading operating system for the Indian market. It unifies terminal-grade market exploration (multi-asset, multi-timeframe), depth research and analytics, live decision support with regime/signal awareness, options strategy intelligence, broker-integrated execution (Dhan-first via OpenAlgo), modular data pipelines, operational observability, and extensibility via plugins.

## What It Is NOT

- A plain broker terminal (Sensibull, OptionChain, etc.)
- A plain analytics terminal (like FinceptTerminal breadth)
- A pure strategy bot (like ShettyBot V1 was becoming)
- A charting-only platform (TradingView competitor)
- A backtesting-only framework

## Core Differentiators

1. India-first market structure baked in (not adapted from international)
2. Dhan-native integration — first-class, not an adapter afterthought
3. OpenAlgo-powered execution — delegate, don't duplicate
4. ShettyBot's intelligence layer preserved and modularized
5. Phase-gated delivery from useful product to powerful platform

## Primary Users

- **Prosumer/retail traders** in Indian markets (NSE/BSE) — equities, indices, F&O
- **Options traders** needing strategy intelligence beyond Greeks
- **Research-oriented traders** who want market-microscope capabilities
- **The operator** — one person managing portfolio, scanning for setups, executing

## Key Reference Systems

| System | Role |
|--------|------|
| OpenAlgo | Execution backbone, broker abstraction |
| DhanHQ-py | Dhan-specific deep integration |
| ShettyBot V1 | Intelligence/decision layer origin |
| FinceptTerminal | Multi-asset terminal reference |
