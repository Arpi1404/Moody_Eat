# Mobile Polish Notes

Audited at a 375px-wide viewport against the primary phone flows.

## Verified

- Home, saved, journal, quest preview, share sheet, and journal capture sheet were smoke-tested at 375px width.
- Viewport meta now includes `viewport-fit=cover`.
- Fixed-position bottom nav, quest action bar, toasts, and sheets use safe-area padding.
- Bottom sheets use dynamic viewport sizing and internal scrolling so controls stay reachable above iOS browser chrome.
- Text inputs and selects are at least 16px to avoid iOS focus zoom.
- Primary buttons, nav items, sheet controls, stop checkboxes, swap controls, and page CTAs have at least 44px tap areas.
- Quest map stays contained in the page layout at phone width.

## Notes

- The browser automation screenshot canvas captured extra empty space to the right, but the app content itself stayed constrained to the phone-width column and no page controls were clipped.
- `npm --prefix frontend run build` passes.
- `npm --prefix frontend run lint` is blocked by the existing local `chalk` module resolution issue in `frontend/node_modules`, not by these mobile changes.
- The IDE still reports a stale `JournalSheet` module diagnostic in `QuestPage.tsx`; the production TypeScript build resolves it successfully.
