# ADR-011: Complete Frontend + Backend API Refactor with shadcn-svelte

## Status
Accepted (2026-08-12)

## Context
After completing 6 phases of development (P0-P5), the application has comprehensive functionality but critical UI/UX issues:
- Data not loading in watchlist, option chain, proposals
- Broken interactions (log drawer, watchlist add, SERP dropdown)
- Design debt accumulated across rapid feature development
- Research/Knowledge panels described as "way too ugly"
- Tests passing but actual user experience broken

The root cause is not individual bugs but architectural decisions made during rapid development that prioritized functionality over usability and maintainability.

## Decision
**Complete refactor of frontend + backend API** using:
- **Design System**: shadcn-svelte (Svelte 5 port of shadcn-ui)
- **Design Language**: awesome-design-md principles
- **Migration Strategy**: Incremental with parallel build

### Scope
- **Frontend**: Complete rebuild of all Svelte components with shadcn-svelte
- **Backend API**: Redesign contracts, data models, component architecture
- **Migration**: Build new system alongside old, migrate feature-by-feature, cut over only after validation

### What We're NOT Doing
- Bug-fix-only approach (addresses symptoms, not root causes)
- Big-bang rewrite (too risky, no incremental validation)
- Feature-by-feature replacement without parallel build (no rollback capability)

## Consequences

### Positive
- Professional, modern UI suitable for production use
- Consistent design language across all components
- Accessible components out of the box (shadcn-svelte)
- Solid foundation for future feature development
- Better separation of concerns between frontend and backend
- Type-safe API contracts

### Negative
- Larger scope than bug-fix-only approach
- More development time upfront
- Temporary duplication during parallel build phase
- Need to maintain two API versions during migration

### Neutral
- Existing tests remain valid (business logic unchanged)
- Backend core logic (intelligence, execution, risk) stays intact
- Only API layer and presentation change

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
1. Set up shadcn-svelte in the project
2. Create design token system (colors, spacing, typography)
3. Build base component library (Button, Input, Card, Dialog, etc.)
4. Create new API contract definitions (OpenAPI/TypeSpec)

### Phase 2: Critical Features (Week 3-4)
1. Watchlist (new API + new UI)
2. Option Chain (new API + new UI)
3. Header/Navigation (new UI)
4. Connection state management (fix current bugs)

### Phase 3: Intelligence Features (Week 5-6)
1. Scanner panel (new UI)
2. Hints panel (new UI)
3. Analytics panel (new UI)
4. Greeks panel (new UI)

### Phase 4: Execution Features (Week 7-8)
1. Proposals (new API + new UI)
2. Orders (new API + new UI)
3. Positions (new API + new UI)
4. Risk heat map (new UI)

### Phase 5: Research & Knowledge (Week 9-10)
1. Research panel (complete redesign)
2. Knowledge panel (complete redesign)
3. Settings (new UI)

### Phase 6: Cutover (Week 11-12)
1. Final validation of all features
2. Performance testing
3. Documentation update
4. Remove old system
5. Deploy new system

## Rollback Plan
During parallel build phase, old system remains fully functional. If new system has critical issues:
- Revert routing to old system
- Fix issues in new system
- Re-attempt cutover

## References
- [shadcn-svelte](https://www.shadcn-svelte.com/)
- [awesome-design-md](https://github.com/VoltAgent/awesome-design-md)
- [Svelte 5 Runes](https://svelte.dev/docs/svelte/$state)
