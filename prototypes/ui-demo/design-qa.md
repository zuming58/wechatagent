# UI Demo Design QA

## Comparison target

- Source visual truth: `reference/relationship-workbench-final-bright-blue.png`
- Implementation screenshot: `reference/implementation-final-bright-blue-1440x1024.png`
- Same-comparison evidence: `reference/qa-comparison-final-bright-blue.png`
- Viewport: 1440 x 1024 CSS px, desktop relationship overview, device scale factor 1.
- Source pixels: 1440 x 1024. Implementation pixels: 1440 x 1024. No density normalization was required.

## Evidence and state

The comparison image places the approved visual truth beside the browser-rendered implementation at the same viewport. Both are the default desktop relationship-overview state: first contact selected, no drawer open, no search filter, and no transient confirmation state.

Focused comparison was made for the left navigation, selected contact, profile header, semantic panels, action buttons, and evidence timeline. A separate focused crop was not saved because the combined image retains readable visual detail at the 1:1 source resolution.

## Comparison history

### Iteration 1 — blocked

- [P1] The previous implementation used a muted gray-blue/navy palette that contradicted the approved bright-blue reference.
- [P1] The previous navigation lacked the slim vivid-blue brand stripe and used pale selected controls instead of the reference's bright-blue selected navigation.

Fix applied: replaced the theme tokens and all affected navigation, contact, workspace, panel, action, drawer, and focus states with the approved bright-blue/light-neutral system. The final capture above is the post-fix evidence.

## Required fidelity surfaces

- **Fonts and typography:** Inter/PingFang/Microsoft YaHei system stack, compact 9–21px hierarchy, clear title/action weights, and controlled one-line truncation match the dense desktop-workbench intent. Chinese fallback remains readable at 1440px.
- **Spacing and layout rhythm:** browser capture preserves the three panes, compact header, wide white working canvas, narrow dividers, low-radius cards, and restrained elevation. No persistent control is clipped.
- **Colors and tokens:** vivid `#1677FF` is restricted to primary actions, active states, selected indicators, and links. Navigation is neutral `#F5F6F8`; the contact pane is cool white; workspace is white. Green, ice blue, warm yellow, and lavender remain semantic accents only.
- **Image quality and asset fidelity:** the approved source uses portrait imagery, but the product requirement explicitly permits initial-based avatars when no real locally cached avatar is available. The implementation uses this intentional fallback, not a fabricated portrait; Phosphor icons supply the UI iconography.
- **Copy and content:** all visible content represents the selected contact, local-only state, evidence, suggestions, needs, and tasks. Search, contact selection, tabs, confirmation/ignore controls, task toggle, evidence drawer, and contextual search are operational.

## Browser interaction and console checks

- Tested: contact filtering, opening the evidence tab, returning to overview, confirming an AI suggestion, opening contact-scoped search, and evidence drawer visibility.
- Result: all tested controls changed state as expected; no page errors or browser console errors were observed.

## Findings

No actionable P0, P1, or P2 visual differences remain. The intentional portrait-to-initial avatar fallback is documented above and follows the agreed avatar policy.

## Follow-up polish

- [P3] Replace initials automatically with the latest locally cached WeChat avatar once the connector provides one.

final result: passed
