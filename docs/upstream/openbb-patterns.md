# OpenBB Pattern Analysis for ShettyXtreme

**Date:** 2026-07-12 | **License:** AGPL-3.0 (pattern study only, no code used)

## What OpenBB Actually Is

Open Data Platform (ODP) by OpenBB is an open-source Python financial SDK with 31 data providers, 15+ analytical extensions, REST API generation, MCP server, and desktop app. 1,295 Python files, 235MB.

## Key Architectural Patterns to Extract

### 1. Provider/Fetcher Abstraction (CRITICAL - Phase 1)

Generic Fetcher[QueryParams, Data] with 3-step pipeline:
```
transform_query(params) -> provider-specific query
extract_data(query, credentials) -> raw API response
transform_data(query, data) -> normalized standard model
```
This is EXACTLY our anti-corruption layer design validated by 31 providers.

### 2. Standard Models (Phase 1)

OpenBB defines Pydantic models for every data type that ALL providers implement against.
The model IS the contract. We should do the same for Bar, Tick, Quote, OptionsChain, Order, Position.

### 3. Router/Command Pattern (Phase 2)

Router class with @router.command(model="ModelName") decorator auto-generates:
- FastAPI REST endpoints
- Python SDK methods
- MCP tool definitions
- Example snippets

### 4. Provider Interface Singleton (already planned)

Registry of all providers and their capabilities: models supported, credentials needed, params accepted.

### 5. Cookiecutter Plugin Scaffold (Phase 3)

Templated provider/extension creation with correct structure, dependencies, and test stubs.

### 6. MCP Server Extension (Phase 3+)

Exposes all financial commands as MCP tools for AI agents.

## What We Do NOT Need

- Data providers (global markets, not India)
- REST API code (we have event bus)
- Web UI (we build terminal UI)
- Econometrics/economic data (out of scope)
