# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

## Confirmed design direction

- Source visual: the third generated “关系记忆工作台” direction, refined after user selection.
- Preserve a three-pane desktop information architecture: light module navigation, searchable contact list, and a large relationship workspace.
- Overall tone must be bright, simple, and immediately understandable for WeChat-heavy professional use.
- Use subtle semantic surface tints to distinguish modules: pale mint for confirmed facts, pale blue for AI suggestions, pale warm yellow for needs, pale lavender/cool gray for tasks, and white for the evidence timeline.
- Keep shadows minimal, borders soft, and saturated color limited to state meaning and primary actions.
- Demo must support core interactions: contact selection, tabs, search, confirming/ignoring AI suggestions, completing tasks, and opening evidence context.
- Avatar handling is not a manual profile-maintenance feature: render the latest locally cached WeChat avatar when available, fall back to the display-name initial, refresh automatically during incremental sync, and identify contacts by a stable internal WeChat-derived key rather than avatar, nickname, or real name.
