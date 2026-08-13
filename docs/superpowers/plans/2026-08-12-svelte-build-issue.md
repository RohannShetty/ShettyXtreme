# Svelte 5 Runes Not Compiling — Root Cause & Fix

**Date:** 2026-08-12
**Status:** Investigation complete — root cause identified, fix proposed
**Blocking:** Entire UI (blank screen, `Uncaught ReferenceError: $state is not defined`)

## Symptom

- Server runs, but the UI renders blank.
- Browser console: `Uncaught ReferenceError: $state is not defined`.
- `vite build` succeeds, and the output bundle contains `$state` as a raw runtime
  reference instead of compiled reactivity code.
- Bundle hash appears not to change across rebuilds.

## Root Cause

**`src/shettyxtreme/terminal/web/src/lib/connection.ts:22` uses the `$state` rune
in a plain `.ts` file.**

```ts
// src/lib/connection.ts (line 22)
export const connectionStore: ConnectionInfo = $state({
  state: "unknown",
  detail: "",
});
```

In Svelte 5, runes (`$state`, `$derived`, `$effect`, `$props`, `$bindable`, …) are
**compiler-only syntax**. They are compiled by the Svelte compiler in exactly two
file kinds:

1. `.svelte` component files
2. **`.svelte.js` / `.svelte.ts`** module files

A plain `.ts` / `.js` file is handled by esbuild/rollup **without the Svelte
compiler**, so `$state(...)` passes through verbatim into the bundle. At runtime,
`$state` is not a defined identifier (there is no runtime export to import it
from), so the module throws `ReferenceError` the moment it evaluates.

Because `connection.ts` is imported by `Header.svelte` (via
`App.svelte` ← `main.ts`), the whole module graph fails to evaluate and **nothing
renders** — a blank UI.

### Proof in the shipped bundle

`src/shettyxtreme/terminal/static/assets/index-lwfCvaXz.js` (position ~338516):

```js
const ls=$state({state:"unknown",detail:""});
```

This is the un-compiled `connection.ts` body. The rest of the bundle is correctly
compiled Svelte 5 output (scoped classes like `svelte-h6ragi`, client runtime
helpers `m()`, `n()`, `E()`), which proves the Svelte compiler **is** running and
working for `.svelte` files — it just never processes `connection.ts`.

### Why the configs looked innocent (they are)

Verified — **all Svelte tooling is correctly configured and at the right versions:**

| Check | Result |
|---|---|
| `web/vite.config.ts` | `plugins: [tailwindcss(), svelte()]` — correct, no missing plugin |
| `web/svelte.config.js` | `vitePreprocess()` only — harmless, no competing config |
| Installed versions | `svelte` 5.56.8, `@sveltejs/vite-plugin-svelte` 5.1.1, `vite` 6.4.3 — all correct |
| `web/tsconfig.json` | No `compilerOptions` disabling runes; `include` covers `src/**/*.ts` |
| Only one config set | No stray `vite.config.*` / `svelte.config.*` elsewhere in the repo |
| Server mount | FastAPI mounts `terminal/static` at `/static` — matches vite `outDir: "../static"` |
| Plugin rune-module support | Plugin `buildModuleFilter` matches `.svelte.` infix + `.js`/`.ts` extension — i.e. `connection.svelte.ts` **would** be compiled; `connection.ts` is not |

### Why the bundle hash "doesn't change"

The build pipeline is fine. Git status shows the previous bundle
(`index-CkQ5uwKI.js`) deleted and a fresh bundle (`index-lwfCvaXz.js`) written —
the hash **did** change when the new code was built. What doesn't change: the
broken `$state` bytes, because they are emitted deterministically on every
rebuild of the same (broken) source. No amount of rebuilding fixes it — the
source file itself must change.

Note: `src/lib/connection.ts` is **untracked** (never committed) — it arrived as
part of in-progress work (comment references "P1-2.4") and slipped past the
Svelte 5 file-naming rule.

## Proposed Fix

**Rename `connection.ts` → `connection.svelte.ts` and import it with the full
extension.**

1. `git mv` / rename:
   `src/shettyxtreme/terminal/web/src/lib/connection.ts`
   → `src/shettyxtreme/terminal/web/src/lib/connection.svelte.ts`

2. Update the only importer, `src/components/Header.svelte` (line 12):

   ```ts
   // from
   import { connectionStore, applyServerState, applyHealthState, applyLocalWsState } from "../lib/connection";
   // to (explicit extension — required, see note)
   import { connectionStore, applyServerState, applyHealthState, applyLocalWsState } from "../lib/connection.svelte.ts";
   ```

   **Why the explicit extension is required:** vite-plugin-svelte only patches
   `resolve.mainFields` and `resolve.conditions`, **not** `resolve.extensions`.
   Vite's default extension resolution list (`['.mjs', '.js', '.mts', '.ts',
   '.jsx', '.tsx', '.json']`) does not include `.svelte.ts`, so the extensionless
   import `"../lib/connection"` would fail to resolve after the rename. Using the
   full filename makes resolution exact and unambiguous.

   (Alternative if extensionless import must be kept: add
   `resolve: { extensions: [".svelte.ts", ".svelte.js", ...] }` to
   `vite.config.ts` — but the explicit-extension import is the simpler, more
   idiomatic Svelte 5 pattern.)

3. Optionally add a repo-wide guard so this class of bug can't recur:
   grep for runes in plain `.ts`/`.js` files:
   ```bash
   grep -rnE '\$(state|derived|effect|props|bindable|inspect|host)\b' --include='*.ts' --include='*.js' src/shettyxtreme/terminal/web/src | grep -v '\.svelte\.'
   ```
   Expect zero matches (outside `.svelte.ts` / `.svelte.js` / `.svelte` files).

## Scope of Change

- 1 rename + 1 import-line edit (tiny-fix territory per AGENTS.md — no spec/plan
  ritual needed for the fix itself; this doc is the investigation record).
- No API/schema change. No behavior change — `connectionStore` semantics stay
  identical; it just becomes truly reactive (compiled) instead of throwing.

## Verification Steps

1. **Rename** the file and update the Header import as above.

2. **svelte-check type gate** (from `web/`):
   ```powershell
   npm run check
   ```
   Expect 0 errors. (svelte-check understands runes in `.svelte.ts` files;
   tsconfig `include: ["src/**/*.ts", …]` already covers the new filename.)

3. **Rebuild** (from `src/shettyxtreme/terminal/web`):
   ```powershell
   npm run build
   ```

4. **Assert the raw rune is gone** from the new bundle:
   ```powershell
   # PowerShell
   $bundle = Get-ChildItem ../static/assets/*.js | Sort-Object LastWriteTime | Select-Object -Last 1
   Select-String -Path $bundle.FullName -Pattern '\$state\('   # expect NO matches
   ```
   The only legitimate `$state` occurrence in a healthy bundle is the Svelte
   runtime's `Symbol("$state")` — a bare `$state(...)` **call** must not exist.

5. **Frontend tests** (from `web/`):
   ```powershell
   npm run test
   ```

6. **Manual smoke test:** start the terminal (`.venv\Scripts\python.exe run.py
   --mode OBSERVER`), open the browser, confirm the UI renders (header connection
   pip included) and the console is free of `$state` errors. Hard-refresh
   (Ctrl+F5) to bypass any cached broken bundle.

7. If the server process is already running with a cached bundle, restart it or
   clear browser cache — the static dir is re-served fresh on each request, but a
   cached `index-*.js` in the browser will keep showing the old error.

## Files Touched (for the fix)

- `src/shettyxtreme/terminal/web/src/lib/connection.ts` → renamed to
  `connection.svelte.ts`
- `src/shettyxtreme/terminal/web/src/components/Header.svelte` (import line)
- Rebuilt bundle in `src/shettyxtreme/terminal/static/assets/` (committed output)

## Guardrails for the future

- **Rule to remember:** in Svelte 5, runes only compile in `.svelte`,
  `.svelte.js`, and `.svelte.ts` files. Any plain `.ts`/`.js` file that wants
  reactivity must be renamed with the `.svelte.` infix.
- Consider adding the grep guard (step 3 of the fix) to the manual test gates in
  AGENTS.md so a stray rune in a `.ts` file can't ship a blank UI again.
