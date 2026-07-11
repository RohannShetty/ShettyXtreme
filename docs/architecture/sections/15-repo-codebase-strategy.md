# Section 15: Repo / Codebase Strategy
Modular monolith with strict boundaries under src/shettyxtreme/{core,integration,intelligence,terminal,data,execution,risk,options,research,observability,plugins}. Package boundaries enforced by CI import checks. core has zero external imports. integration is only bridge to external packages. Version: semver 0.1.0.
