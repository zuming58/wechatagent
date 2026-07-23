# Prototype Instructions

Run the local server yourself and open the preview in the browser available to this environment. Do not give the user server-start instructions when you can run it.

Before making substantial visual changes, use the Product Design plugin's `get-context` skill when the visual source is unclear or no longer matches the current goal. When the user gives durable prototype-specific design feedback, preferences, or decisions, record them in `AGENTS.md`.

When implementing from a selected generated mock, treat that image as the source of truth for layout, component anatomy, density, spacing, color, typography, visible content, and hierarchy.

Build app UI in `src/`. Keep `.openai/hosting.json`, `worker/index.js`, `scripts/prepare-sites-build.mjs`, and `tests/sites-worker.test.mjs` intact so the same local prototype can be handed to Sites. Before a Sites handoff, run `npm run build` and `npm run test:sites`; the build must leave `dist/client/index.html`, `dist/server/index.js`, and `dist/.openai/hosting.json`.

## Confirmed design direction

- Source visual: `reference/relationship-workbench-final-bright-blue.png`. It is the only implementation target; older green, dark-navy, and gray-blue references are historical context only.
- Preserve a three-pane desktop information architecture: light module navigation, searchable contact list, and a large relationship workspace.
- Overall tone must be bright, simple, and designed, with no dusty gray-blue or foggy cast.
- Use a very light neutral-gray main navigation with a slim vivid-blue brand stripe. Use #1677FF for active navigation, primary actions, active tabs, links, and selection indicators. Keep the contact column cool white/light sky and the relationship workspace predominantly pure white.
- Preserve semantic color: confirmed facts and sync success green, AI suggestions ice blue, needs pale warm yellow, tasks pale lavender, and evidence white. Do not use gradients or a full-height dark-blue navigation wall.
- Keep shadows minimal, borders soft, and saturated color limited to state meaning and primary actions.
- Demo must support core interactions: contact selection, tabs, search, confirming/ignoring AI suggestions, completing tasks, and opening evidence context.
- Avatar handling is not a manual profile-maintenance feature: render the latest locally cached WeChat avatar when available, fall back to the display-name initial, refresh automatically during incremental sync, and identify contacts by a stable internal WeChat-derived key rather than avatar, nickname, or real name.
